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
//import {StrategyAPI} from "@yearnvaults/contracts/BaseStrategy.sol";
import {StrategyAPI} from "../interfaces/IStrategy.sol";
import {IGelatoOps} from "../interfaces/IGelato.sol";
import {LibDataTypes} from "../interfaces/libraries/LibDataTypes.sol";
import {ICommonReportTrigger} from "../interfaces/ICommonReportTrigger.sol";

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
    // An enum to list all supported jobs in the contract
    enum jobTypes {
        MONITOR,
        HARVEST,
        TEND
    }

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

    // commonReportTrigger is the the central contract that keepers should use to decide if Yearn V3 strategies should report profits as well as when a V3 Vaults should record a strategies profits.
    ICommonReportTrigger public commonReportTrigger;

    // Yearn accounts
    address public owner;
    address public keeper;
    address public pendingGovernance;
    address payable public governance;

    // Yearn modifiers
    modifier onlyKeepers() {
        require(
            msg.sender == owner ||
                msg.sender == governance ||
                msg.sender == keeper,
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

    // `JobCreated` is an event we emit when there's a succesful harvest
    event JobCreated(
        address indexed strategy,
        jobTypes indexed jobType,
        bytes32 jobId
    );

    // `HarvestByGelato` is an event we emit when there's a succesful harvest
    event HarvestByGelato(address indexed strategy, uint256 gelatoFee);

    // `TendByGelato` is an event we emit when there's a succesful tend
    event TendByGelato(address indexed strategy, uint256 gelatoFee);

    constructor(address lensAddress, address gelatoAddress, address commonReportTriggerAddress) {
        // Set owner and governance
        owner = msg.sender;
        keeper = gelatoAddress;
        governance = payable(msg.sender);

        // Set Yearn Lens address
        lens = IYearnLens(lensAddress);

        // Set Gelato Ops
        ops = IGelatoOps(gelatoAddress);

        // Set CommonReportTrigger
        commonReportTrigger = ICommonReportTrigger(commonReportTriggerAddress);
    }

    /**
    @notice Creates Gelato harvest job for a strategy and pays Gelato for creating the job. 
    @param strategyAddress Strategy Address for which a harvest job will be created
    */
    function createHarvestJob(address strategyAddress) external onlyKeepers {
        // Create job and add it to the Gelato registry
        createJob(jobTypes.HARVEST, strategyAddress);

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
    @param jobType Enum determining job type
    @param strategyAddress Strategy address for which a job will be created
    */
    function createJob(jobTypes jobType, address strategyAddress)
        public
        onlyKeepers
    {
        LibDataTypes.ModuleData memory moduleData = getModuleData(
            jobType,
            strategyAddress
        );

        bytes memory execData = getJobData(jobType, strategyAddress);

        bytes32 jobId = ops.createTask(
            address(this),
            execData,
            moduleData,
            feeToken
        );

        emit JobCreated(strategyAddress, jobType, jobId);
    }

    /**
    @notice Cancel a Gelato job given a strategy address and job type
    @dev Important: you must remove yGO as the keeper before cancelling the task; 
    otherwise, the strategy monitor will pick up the job again and restart it.
    @param jobType Enum determining job type
    @param strategyAddress Strategy for which to cancel a job    
    */
    function cancelJob(jobTypes jobType, address strategyAddress)
        external
        onlyAuthorized
        returns (bytes32 cancelledJobId)
    {
        require(
            StrategyAPI(strategyAddress).keeper() != address(this),
            "!removed"
        );
        bytes32 cancelledJobId = getJobId(jobType, strategyAddress);
        ops.cancelTask(cancelledJobId); // dev: reverts if non-existent
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
            bytes32 jobId = getJobId(jobTypes.HARVEST, strategies[i]);
            if (jobId == 0) {
                canExec = true;
                execPayload = getJobData(jobTypes.MONITOR, strategies[i]);
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

        // Make sure yGO is the keeper of the strategy.
        if (strategy.keeper() != address(this)) {
            execPayload = bytes(
                "Strategy not onboarded to yGO for harvest operations"
            );
            return (canExec, execPayload);
        }

        // yearn-v3: we pass the strategy address to the CommonReportTrigger to check for reportTrigger
        (canExec, ) = commonReportTrigger.strategyReportTrigger(strategyAddress);

        // If we can execute, prepare the payload
        if (canExec) {
            execPayload = getJobData(jobTypes.HARVEST, strategyAddress);
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

        // Make sure yGO is the keeper of the strategy.
        if (strategy.keeper() != address(this)) {
            execPayload = bytes(
                "Strategy not onboarded to yGO for tend operations"
            );
            return (canExec, execPayload);
        }
        return (canExec, execPayload);

        // yearn-v3: we pass the strategy address to the CommonReportTrigger to check for tendTrigger
        (canExec, ) = commonReportTrigger.strategyTendTrigger(strategyAddress);

        // If we can execute, prepare the payload
        if (canExec) {
            execPayload = getJobData(jobTypes.TEND, strategyAddress);
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

        // Re-run strategyReportTrigger() to ensure the tx makes economic sense.
        // yearn-v3: we pass the strategy address to the CommonReportTrigger to check for reportTrigger
        (bool shouldReport, ) = commonReportTrigger.strategyReportTrigger(strategyAddress);
        require(shouldReport, "!economic");

        strategy.report();

        // Pay Gelato for the service.
        payKeeper(gelatoFee);

        emit HarvestByGelato(strategyAddress, gelatoFee);
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

        // Re-run strategyTendTrigger() to ensure the tx makes economic sense.
        // yearn-v3: we pass the strategy address to the CommonReportTrigger to check for tendTrigger
        (bool shouldTend, ) = commonReportTrigger.strategyTendTrigger(strategyAddress);
        require(shouldTend, "!economic");

        strategy.tend();

        // Pay Gelato for the service.
        payKeeper(gelatoFee);

        emit TendByGelato(strategyAddress, gelatoFee);
    }

    /**
    @notice Build call data used by the keeper to execute the job once it's workable
    @param jobType Enum determining job type
    @param strategyAddress Strategy address for which the call data will be created
    */
    function getJobData(jobTypes jobType, address strategyAddress)
        public
        view
        returns (bytes memory jobSelector)
    {
        if (jobType == jobTypes.HARVEST) {
            jobSelector = abi.encodeCall(
                this.harvestStrategy,
                (strategyAddress)
            );
        } else if (jobType == jobTypes.TEND) {
            jobSelector = abi.encodeCall(this.tendStrategy, (strategyAddress));
        } else if (jobType == jobTypes.MONITOR) {
            jobSelector = abi.encodeCall(
                this.createHarvestJob,
                (strategyAddress)
            );
        }
    }

    /**
    @notice Get gelato module used to check for the workable status of a job. 
    @param jobType Enum determining job type
    @param strategyAddress Strategy address to check job status for
    @dev Note that `strategyAddress` is not needed when `jobTypes` is jobTypes.MONITOR
    */
    function getModuleData(jobTypes jobType, address strategyAddress)
        public
        view
        returns (LibDataTypes.ModuleData memory moduleData)
    {
        moduleData = LibDataTypes.ModuleData(
            new LibDataTypes.Module[](1),
            new bytes[](1)
        );

        // All job types use the same module type
        moduleData.modules[0] = LibDataTypes.Module.RESOLVER;

        if (jobType == jobTypes.MONITOR) {
            moduleData.args[0] = abi.encode(
                address(this),
                abi.encodeCall(this.checkNewStrategies, ())
            );
        } else if (jobType == jobTypes.HARVEST) {
            moduleData.args[0] = abi.encode(
                address(this),
                abi.encodeCall(this.checkHarvestTrigger, (strategyAddress))
            );
        } else if (jobType == jobTypes.TEND) {
            moduleData.args[0] = abi.encode(
                address(this),
                abi.encodeCall(this.checkTendTrigger, (strategyAddress))
            );
        }
    }

    /**
    @notice Get function selector from `jobData`. Used to id the job in the Gelato contract.
    @param jobData Call data used by the keeper to execute the job once it's workable
    */
    function extractSelector(bytes memory jobData)
        internal
        pure
        returns (bytes4 selector)
    {
        selector =
            jobData[0] |
            (bytes4(jobData[1]) >> 8) |
            (bytes4(jobData[2]) >> 16) |
            (bytes4(jobData[3]) >> 24);
    }

    /**
    @notice Query the Gelato job id contract storage and return a job id if the task exists.
    @param jobType Enum determining job type
    @param strategyAddress Strategy address for the job to query
    */
    function getJobId(jobTypes jobType, address strategyAddress)
        public
        view
        returns (bytes32 jobId)
    {
        LibDataTypes.ModuleData memory moduleData = getModuleData(
            jobType,
            strategyAddress
        );

        bytes memory jobData = getJobData(jobType, strategyAddress);

        bytes4 selector = extractSelector(jobData);

        jobId = ops.getTaskId(
            address(this),
            address(this),
            selector,
            moduleData,
            feeToken
        );

        bytes32[] memory jobIds = ops.getTaskIdsByUser(address(this));

        for (uint256 i = 0; i < jobIds.length; i++) {
            if (jobId == jobIds[i]) {
                return jobId;
            }
        }
        delete jobId;
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
    @notice Changes the `commonReportTrigger` address.
    @param _commonReportTrigger The new address to assign as `commonReportTrigger`.
    */
    function setCommonReportTrigger(address _commonReportTrigger) external onlyAuthorized {
        require(_commonReportTrigger != address(0));
        commonReportTrigger = ICommonReportTrigger(_commonReportTrigger);
    }

    /**
    @notice Changes the `owner` address.
    @param _owner The new address to assign as `owner`.
    */
    function setOwner(address _owner) external onlyAuthorized {
        require(_owner != address(0));
        owner = _owner;
    }

    /**
    @notice Changes the `keeper` address.
    @param _keeper The new address to assign as `keeper`.
    */
    function setKeeper(address _keeper) external onlyAuthorized {
        require(_keeper != address(0));
        keeper = _keeper;
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
