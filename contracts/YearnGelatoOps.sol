// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.8.15;

/**
@title Yearn Gelato Ops
@author yearn.finance
@notice Yearn Gelato Ops or yGO is a smart contract that leverages Gelato to automate
the harvests and tends of strategies that have yGO assigned as its keeper.
The contract provides the Gelato network of keepers Yearn harvest and tend jobs that
are ready to execute, and it pays Gelato after a succesful harvest. The contract detects 
when a new stragegy is using it as its keeper and creates a Gelato harvest job automatically. 
Tend jobs must be added manually.
@dev We use Lens to detect new strategies, but Lens does not include strategies that are
not in a vault's withdrawal queue. This is not expected all the time, but it can happen.
*/

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {StrategyAPI} from "@yearnvaults/contracts/BaseStrategy.sol";
import {IGelatoOps} from "../interfaces/IGelato.sol";
import {LibDataTypes} from "../interfaces/libraries/LibDataTypes.sol";

/**
@title Yearn Lens Interface
@notice We leverage the Yearn Lens set of contracts to obtain an up-to-date
snapshot of active strategies in production.
 */
interface IYearnLens {
    // Lens Strategy Helper
    function assetsStrategiesAddresses()
        external
        view
        returns (address[] memory);
}

contract YearnGelatoOps {
    // `jobIds` keeps track of the Gelato job IDs for each strategy. A job
    // ID is stored for each type of job currently supported - harvest and
    // tend. Note that if a jobId exists, it does not necesarily mean that
    // the job is active.
    struct jobId {
        bytes32 harvest;
        bytes32 tend;
    }

    mapping(address => jobId) public jobIds;

    // `feeToken` is the crypto used for payment.
    address internal constant feeToken =
        0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE;

    // `maxFee` determines the max fee allowed to be paid to Gelato
    // denominated in `feeToken`. Note that setting it to 0 would
    // effectively prevent all executors from running any task.
    // To change its value, call `setMaxFee()`
    uint256 public maxFee = 1e16;

    // Yearn Lens data lens
    IYearnLens internal immutable lens;

    // Gelato Ops Proxy contract
    IGelatoOps internal immutable ops;

    // Yearn accounts
    address public owner;
    address public pendingGovernance;
    address payable public governance;

    // Yearn modifiers
    modifier onlyKeepers() {
        require(
            msg.sender == owner ||
                msg.sender == governance ||
                msg.sender == address(ops),
            "!keeper"
        );
        _;
    }

    modifier onlyAuthorized() {
        require(msg.sender == owner || msg.sender == governance, "!authorized");
        _;
    }

    modifier onlyGovernance() {
        require(msg.sender == governance, "!governance");
        _;
    }

    // `HarvestByGelato` is an event we emit when there's a succesful harvest
    event HarvestByGelato(bytes32 jobId, address strategy, uint256 gelatoFee);

    // `TendByGelato` is an event we emit when there's a succesful tend
    event TendByGelato(bytes32 jobId, address strategy, uint256 gelatoFee);

    constructor(address _lens, address _gelatoOps) {
        // Set owner and governance
        owner = msg.sender;
        governance = payable(msg.sender);

        // Set Yearn Lens address
        lens = IYearnLens(_lens);

        // Set Gelato Ops
        ops = IGelatoOps(_gelatoOps);
    }

    /**
    @notice Create Gelato job that will monitor for new strategies in Yearn Lens. When
    a new startegy is detected with its keeper set as yGO, yGO creates a
    gelato job for it. 
    @dev note that the job id is stored under harvest even though the strategy monitoring job 
    does not take care of harvests or tends, but was preferred to creating a 3rd job type in 
    the `jobIds` struct.
    */
    function initiateStrategyMonitor() external onlyAuthorized {
        LibDataTypes.ModuleData memory moduleData = LibDataTypes.ModuleData(
            new LibDataTypes.Module[](1),
            new bytes[](1)
        );
        moduleData.modules[0] = LibDataTypes.Module.RESOLVER;
        moduleData.args[0] = abi.encodeWithSelector(
            this.checkNewStrategies.selector
        );

        bytes memory execSelector = abi.encodeWithSelector(
            this.createHarvestJob.selector
        );

        jobIds[address(this)].harvest = ops.createTask(
            address(this), // `execAddress`
            execSelector,
            moduleData,
            feeToken
        );
    }

    /**
    @notice Creates Gelato harvest job for a strategy and pays Gelato for creating the job. 
    Updates `jobIds`, which we use to log events and to manage the job.
    @param strategyAddress Strategy Address for which a harvest job will be created
    */
    function createHarvestJob(address strategyAddress) external onlyKeepers {
        // Create job and add it to the Gelato registry
        createJob(strategyAddress, true);

        // `gelatoFee` and `gelatoFeeToken` are state variables in the gelato ops contract that
        // are temporarily modified by the executors right before executing the payload. They are
        // reverted to default values when the gelato contract exec() method wraps up.
        (uint256 gelatoFee, address gelatoFeeToken) = ops.getFeeDetails();

        require(gelatoFeeToken == feeToken, "!token"); // dev: gelato not using intended token
        require(gelatoFee <= maxFee, "!fee"); // dev: gelato executor overcharnging for the tx

        // Pay Gelato for the service.
        payKeeper(gelatoFee);
    }

    /**
    @notice Creates Gelato job for a strategy. This function can be used to manually create either 
    a tend or harvest job. 
    @param strategyAddress Strategy address for which a job will be created
    @param isHarvest boolean indicating whether we create a harvest or a tend job.
    */
    function createJob(address strategyAddress, bool isHarvest)
        public
        onlyKeepers
    {
        bytes32 _jobId;

        LibDataTypes.ModuleData memory moduleData = LibDataTypes.ModuleData(
            new LibDataTypes.Module[](1),
            new bytes[](1)
        );

        if (isHarvest) {
            moduleData.modules[0] = LibDataTypes.Module.RESOLVER;
            moduleData.args[0] = abi.encodeWithSelector(
                this.checkHarvestTrigger.selector,
                strategyAddress
            );

            bytes memory execSelector = abi.encodeWithSelector(
                this.harvestStrategy.selector
            );

            _jobId = ops.createTask(
                address(this), // `execAddress`
                execSelector,
                moduleData,
                feeToken
            );

            // Store job id only once. A job that was created and then cancelled, will
            // have the same job ID if created again
            if (jobIds[strategyAddress].harvest == 0) {
                jobIds[strategyAddress].harvest = _jobId;
            }
        } else {
            moduleData.modules[0] = LibDataTypes.Module.RESOLVER;
            moduleData.args[0] = abi.encodeWithSelector(
                this.checkTendTrigger.selector,
                strategyAddress
            );

            bytes memory execSelector = abi.encodeWithSelector(
                this.tendStrategy.selector
            );

            _jobId = ops.createTask(
                address(this), // `execAddress`
                execSelector,
                moduleData,
                feeToken
            );

            // Store job id only once. A job that was created and then cancelled, will
            // have the same job ID if created again
            if (jobIds[strategyAddress].tend == 0) {
                jobIds[strategyAddress].tend = _jobId;
            }
        }
    }

    /**
    @notice Cancel a Gelato job given a strategy address and job type
    @dev cancelJob(address(this), true) cancels the strategy monitor job
    @param strategyAddress Strategy for which to cancel a job
    @param isHarvest true cancels a harvest job, false cancels a tend job
    */
    function cancelJob(address strategyAddress, bool isHarvest)
        external
        onlyAuthorized
        returns (bytes32 cancelledJobId)
    {
        if (isHarvest) {
            cancelledJobId = jobIds[strategyAddress].harvest;
        } else {
            cancelledJobId = jobIds[strategyAddress].tend;
        }
        ops.cancelTask(cancelledJobId); // dev: reverts if non-existent

        // Important: we don't reset jobIds[strategyAddress].harvest to zero because the
        // strategy monitoring job would otherwise pick it up and restart it, and that's
        // likely not what the user wants. A manual restart is required after a job
        // cancellation.
    }

    /**
    @notice Used by keepers to determine whether a new strategy was added to Yearn Lens
    that has the yGO contract as its keeper. A harvest job is automatically created 
    for newly detected strategies. Tend jobs are not automatically created.
    @return canExec boolean indicating whether a new strategy requires automation.
    @return execPayload call data used by Gelato executors to call createHarvestJob(). It
    includes the address of the strategy to harvest as an input.
    */
    function checkNewStrategies()
        external
        view
        returns (bool canExec, bytes memory execPayload)
    {
        execPayload = bytes("No new strategies to automate");

        // Pull list of active strategies in production
        address[] memory strategies = lens.assetsStrategiesAddresses();

        // Check if there are strategies with yGO assigned as keeper
        for (uint256 i = 0; i < strategies.length; i++) {
            if (StrategyAPI(strategies[i]).keeper() != address(this)) {
                continue;
            }

            // Skip if the job was created before, disregarding current status
            if (jobIds[strategies[i]].harvest == 0) {
                canExec = true;
                execPayload = abi.encodeWithSelector(
                    this.createHarvestJob.selector,
                    strategies[i]
                );
                break;
            }
        }
    }

    /**
    @notice Used by keepers to check whether a strategy is ready to harvest. 
    @param strategyAddress Strategy for which to obtain a harvest status
    @return canExec boolean indicating whether the strategy is ready to harvest
    @return execPayload call data used by Gelato executors to call harvestStrategy(). It
    includes the address of the strategy to harvest as an input parameter.
    */
    function checkHarvestTrigger(address strategyAddress)
        external
        view
        returns (bool canExec, bytes memory execPayload)
    {
        execPayload = bytes("Strategy not ready to harvest");

        // Declare a strategy object
        StrategyAPI strategy = StrategyAPI(strategyAddress);

        // Make sure yGO remains the keeper of the strategy.
        if (strategy.keeper() != address(this)) {
            if (jobIds[strategyAddress].harvest == 0) {
                execPayload = bytes(
                    "Strategy was never onboarded to yGO for harvest operations"
                );
            } else {
                execPayload = bytes(
                    "Strategy no longer automated by yGO for harvest operations"
                );
            }
            return (canExec, execPayload);
        }

        // `callCostInWei` is a required input to the `harvestTrigger()` method of the strategy
        // and represents the expected cost to call `harvest()`. Some blockchains have global
        // variables/functions such as block.basefee or gasUsed() that allow us to estimate the
        // cost to harvest. Not all do, so for now we pass a common, low, fixed cost accross
        // strategies so that the trigger focuses on all other conditions.

        // call the harvest trigger
        canExec = strategy.harvestTrigger(uint256(1e8));

        // If we can execute, prepare the payload
        if (canExec) {
            execPayload = abi.encodeWithSelector(
                this.harvestStrategy.selector,
                strategyAddress
            );
        }
    }

    function checkTendTrigger(address strategyAddress)
        public
        view
        returns (bool canExec, bytes memory execPayload)
    {
        execPayload = bytes("Strategy not ready to tend");

        // Declare a strategy object
        StrategyAPI strategy = StrategyAPI(strategyAddress);

        // Make sure yGO remains the keeper of the strategy.
        if (strategy.keeper() != address(this)) {
            if (jobIds[strategyAddress].tend == 0) {
                execPayload = bytes(
                    "Strategy was never onboarded to yGO for tend operations"
                );
            } else {
                execPayload = bytes(
                    "Strategy no longer automated by yGO for tend operations"
                );
            }
            return (canExec, execPayload);
        }

        // call the tend trigger. Refer to checkHarvestTrigger() for comments on the
        // fixed cost passed to the function.
        canExec = strategy.tendTrigger(uint256(1e8));

        // If we can execute, prepare the payload
        if (canExec) {
            execPayload = abi.encodeWithSelector(
                this.tendStrategy.selector,
                strategyAddress
            );
        }
    }

    /**
    @notice Function that Gelato keepers call to harvest a strategy after `checkHarvestTrigger()`
    has confirmed that it's ready to harvest.
    It checks that the executors are getting paid in the expected crytocurrency and that
    they do not overcharge for the tx. The method also pays executors.
    @dev an active job for a strategy linked to the yGO must exist for executors to be
    able to call this function. 
    @param strategyAddress The address of the strategy to harvest
    */
    function harvestStrategy(address strategyAddress) public onlyKeepers {
        // Declare a strategy object
        StrategyAPI strategy = StrategyAPI(strategyAddress);

        // `gelatoFee` and `gelatoFeeToken` are state variables in the gelato contract that
        // are temporarily modified by the executors before executing the payload. They are
        // reverted to default values when the gelato contract exec() method wraps up.
        (uint256 gelatoFee, address gelatoFeeToken) = ops.getFeeDetails();

        require(gelatoFeeToken == feeToken, "!token"); // dev: gelato not using intended token
        require(gelatoFee <= maxFee, "!fee"); // dev: gelato executor overcharnging for the tx

        // Re-run harvestTrigger() with the gelatoFee passed by the executor to ensure
        // the tx makes economic sense.
        require(strategy.harvestTrigger(gelatoFee), "!economic");

        strategy.harvest();

        // Pay Gelato for the service.
        payKeeper(gelatoFee);

        emit HarvestByGelato(
            jobIds[strategyAddress].harvest,
            strategyAddress,
            gelatoFee
        );
    }

    /**
    @notice Function that Gelato keepers call to tend a strategy after `checkTendTrigger()`
    has confirmed that it's ready to tend.
    It checks that the executors are getting paid in the expected crytocurrency and that
    they do not overcharge for the tx. The method also pays executors.
    @dev an active job for a strategy linked to yGO must exist for executors to be
    able to call this function. 
    @param strategyAddress The address of the strategy to tend
    */
    function tendStrategy(address strategyAddress) external onlyKeepers {
        // Declare a strategy object
        StrategyAPI strategy = StrategyAPI(strategyAddress);

        // `gelatoFee` and `gelatoFeeToken` are state variables in the gelato contract that
        // are temporarily modified by the executors before executing the payload. They are
        // reverted to default values when the gelato contract exec() method wraps up.
        (uint256 gelatoFee, address gelatoFeeToken) = ops.getFeeDetails();

        require(gelatoFeeToken == feeToken, "!token"); // dev: gelato not using intended token
        require(gelatoFee <= maxFee, "!fee"); // dev: gelato executor overcharnging for the tx

        // Re-run tendTrigger() with the gelatoFee passed by the executor to ensure
        // the tx makes economic sense.
        require(strategy.tendTrigger(gelatoFee), "!economic");

        strategy.tend();

        // Pay Gelato for the service.
        payKeeper(gelatoFee);

        emit TendByGelato(
            jobIds[strategyAddress].tend,
            strategyAddress,
            gelatoFee
        );
    }

    /**
    @notice Pays Gelato keepers.
    @param gelatoFee Fee amount to pay Gelato keepers. Determined by the keeper.
    */
    function payKeeper(uint256 gelatoFee) internal {
        address payable gelato = ops.gelato();

        (bool success, ) = gelato.call{value: gelatoFee}("");
        require(success, "!payment");
    }

    /**
    @notice Sets the max fee we allow Gelato to charge for a harvest
    @dev Setting `maxFee` would effectively stop all jobs as they 
    would all start reverting.
    @param _maxFee Max fee we allow Gelato to charge for a harvest.
    */
    function setMaxFee(uint256 _maxFee) external onlyAuthorized {
        maxFee = _maxFee;
    }

    /**
    @notice Changes the `owner` address.
    @param _owner The new address to assign as `owner`.
    */
    function setOwner(address _owner) external onlyAuthorized {
        require(_owner != address(0));
        owner = _owner;
    }

    // 2-phase commit for a change in governance
    /**
    @notice
    Nominate a new address to use as governance.

    The change does not go into effect immediately. This function sets a
    pending change, and the governance address is not updated until
    the proposed governance address has accepted the responsibility.

    @param _governance The address requested to take over yGO governance.
    */
    function setGovernance(address _governance) external onlyGovernance {
        pendingGovernance = _governance;
    }

    /**
    @notice
    Once a new governance address has been proposed using setGovernance(),
    this function may be called by the proposed address to accept the
    responsibility of taking over governance for this contract.

    This may only be called by the proposed governance address.
    @dev
    setGovernance() should be called by the existing governance address,
    prior to calling this function.
    */
    function acceptGovernance() external {
        require(msg.sender == pendingGovernance, "!authorized");
        governance = payable(pendingGovernance);
        delete pendingGovernance;
    }

    /**
    @notice Allows governance to transfer funds out of the contract
    @param _token The address of the token, which balance is to be transfered
    to the governance multisig.
    */
    function sweep(address _token) external onlyGovernance {
        uint256 amount;
        if (_token == feeToken) {
            amount = address(this).balance;
            (bool success, ) = governance.call{value: amount}("");
            require(success, "!transfer");
        } else {
            IERC20 token = IERC20(_token);
            amount = token.balanceOf(address(this));
            token.transfer(governance, amount);
        }
    }

    // enables the contract to receive native crypto
    receive() external payable {}
}
