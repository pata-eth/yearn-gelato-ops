// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

/**
@title Yearn Harvest
@author yearn.finance
@notice Yearn Harvest or yHarvest is a smart contract that leverages Gelato to automate
the harvest of strategies that have yHarvest assigned as its keeper.
The contract provides the Gelato network of keepers Yearn harvest jobs that
are ready to execute, and it pays Gelato after a succesful harvest.
*/

import {SafeMath} from "@openzeppelin/contracts/math/SafeMath.sol";
import {Address} from "@openzeppelin/contracts/utils/Address.sol";
import {SafeERC20, IERC20} from "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";
import {StrategyAPI, VaultAPI, StrategyParams} from "@yearnvaults/contracts/BaseStrategy.sol";
import {IGelatoOps} from "../interfaces/IGelato.sol";

/**
@title Yearn Lens Interface
@notice We leverage the Yearn Lens set of contracts to obtain an up-to-date
snapshot of active strategies in production.
 */
interface IStrategyDataAggregator {
    function assetsStrategiesAddresses()
        external
        view
        returns (address[] memory);
}

contract YearnHarvest {
    using Address for address;
    using SafeMath for uint256;

    // `jobId` keeps track of the Gelato job ID
    bytes32 public jobId;

    // `isActive` indicates whether yHarvest is active. yHarvest is
    // inactive at deployment, activates after creating a job with Gelato, and
    // deactivates after canceling a job with Gelato.
    bool public isActive;

    // `feeToken` is the crypto used for payment.
    address public constant feeToken =
        0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE;

    // `maxFee` determines the max fee allowed to be paid to Gelato
    // denominated in `feeToken`
    uint256 public maxFee = 1e18;

    // `runMaxTime` determines the minimum amount of time that's needed in-between
    // calls to harvest(). The analogous param `minReportDelay` in the strategy is
    // often left at 0, which becomes a problem for yHarvest as the checkHarvestStatus()
    // method in the yHarvest contract would always propose the same strategy to
    // be harvested.
    uint256 public runMaxTime = 3 hours;

    // Yearn Lens data aggregator
    IStrategyDataAggregator internal constant aggregator =
        IStrategyDataAggregator(0x97D0bE2a72fc4Db90eD9Dbc2Ea7F03B4968f6938);

    // Gelato Ops Proxy contract
    IGelatoOps internal constant ops =
        IGelatoOps(0x6EDe1597c05A0ca77031cBA43Ab887ccf24cd7e8);

    // Yearn accounts
    address public management;
    address public owner;
    address payable public governance;
    address payable public pendingGovernance;

    // Yearn modifiers
    // ops.gelato() and address(ops) are the addresses allowed to run 'exec' on the Gelato side
    modifier onlyKeepers() {
        require(
            msg.sender == ops.gelato() ||
                msg.sender == address(ops) ||
                msg.sender == owner ||
                msg.sender == management ||
                msg.sender == governance,
            "!keeper"
        );
        _;
    }

    modifier onlyAuthorized() {
        require(
            msg.sender == owner ||
                msg.sender == management ||
                msg.sender == governance,
            "!authorized"
        );
        _;
    }

    modifier onlyGovernance() {
        require(msg.sender == governance, "!governance");
        _;
    }

    // `HarvestedByGelato` is an event we emit when there's a succesful harvest
    event HarvestedByGelato(
        bytes32 jobId,
        address strategy,
        address gelatoFeeToken,
        uint256 gelatoFee
    );

    constructor() public {
        owner = msg.sender;
        management = msg.sender;
        governance = msg.sender;
    }

    /**
    @notice Used by keepers to check whether a job is ready to run. IMPORTANT: keepers
    are expected to call checkHarvestStatus() as a static, "view" call off-chain.
    @dev The method relies on each strategy to determine whether it's ready for harvest
    (via harvestTrigger()), and attempts a non-state-changing harvest() when the strategy
    trigger returns TRUE.
    Even if the trigger is TRUE and the simulated call to harvest() is succesful, certain
    strategies may have not needed to be harvested (e.g., Total Assets == 0,
    Last run < 10 minutes ago, etc.). This is why we encourage strategists that would like
    to rely on yHarvest for automation to ensure their triggers are accurate to avoid
    unnecesary calls to harvest and the cost associated with it.
    @return canExec boolean indicating whether the strategy is ready to harvest()
    @return execPayload call data used by Gelato executors to call harvestStrategy(). It
    includes the address of the strategy to harvest.
    */
    function checkHarvestStatus()
        external
        onlyKeepers
        returns (bool canExec, bytes memory execPayload)
    {
        // If yHarvest is inactive, don't provide any jobs to keepers/executors
        if (!isActive) return (canExec, execPayload);

        // Pull list of active strategies in production
        address[] memory strategies = aggregator.assetsStrategiesAddresses();

        // Declare a strategy objects
        StrategyAPI strategy_i;
        StrategyParams memory params_i;

        // Last time the strategy was harvested.
        uint256 lastReport;

        // `callCostInWei` is a required input to the `harvestTrigger()` method of the strategy
        // and represents the expected cost to call `harvest()`. Fantom does not currently
        // offer the same global variables/functions that we have in mainnet -- block.basefee or
        // gasUsed() -- to estimate the cost to harvest.
        // For now, yHarvest uses a common, fixed cost accross strategies -- `callCostInWei`.
        // We assign `callCostInWei` a low value so that the trigger focuses on all other conditions.
        uint256 callCostInWei = 1e8;

        // Check active strategies and return the first one that is ready to harvest.
        for (uint256 i = 0; i < strategies.length; i++) {
            // Define `strategy_i`
            strategy_i = StrategyAPI(strategies[i]);

            params_i = VaultAPI(strategy_i.vault()).strategies(strategies[i]);

            // When `minReportDelay` is zero at the strategy level, it's possible that
            // harvestTrigger() could return TRUE. If that were the case, checkHarvestStatus()
            // could find itself returning the same strategy, preventing other strategies that
            // need to be harvest from doing so.
            // To avoid this, we require that a strategy is not run more often than `runMaxTime`.
            lastReport = params_i.lastReport;

            if (now.sub(lastReport) < runMaxTime) continue;

            // To enable automatic harvest() calls, a strategy must have the Yearn Harvest
            // contract as the keeper.
            if (strategy_i.keeper() != address(this)) continue;

            // call the harvest trigger
            canExec = strategy_i.harvestTrigger(callCostInWei);

            // call harvest() and see if it reverts. If it does, move on to the next strategy.
            // If it does not, break loop and return output parameters.
            if (canExec) {
                try strategy_i.harvest() {
                    execPayload = abi.encodeWithSelector(
                        this.harvestStrategy.selector,
                        strategies[i]
                    );
                    break;
                } catch {}
            }
        }
    }

    /**
    @notice This is the executable method that Gelato keepers call to harvest a strategy.
    It checks that the executors are getting paid in the expected crytocurrency and that
    they do not overcharge for the tx. The method also pays executors.
    @param strategyAddress Strategy address to harvest
    */
    function harvestStrategy(address strategyAddress) public onlyKeepers {
        require(isActive, "!active");

        StrategyAPI strategy = StrategyAPI(strategyAddress);
        StrategyParams memory params = VaultAPI(strategy.vault()).strategies(
            strategyAddress
        );

        uint256 lastReport = params.lastReport;

        require(now.sub(lastReport) > runMaxTime, "!time");

        // `gelatoFee` and `gelatoFeeToken` are state variables in the gelato contract that
        // are temporarily modified by the executors before executing the payload. They are
        // reverted to default values when the gelato contract exec() method wraps up.
        (uint256 gelatoFee, address gelatoFeeToken) = ops.getFeeDetails();

        require(gelatoFeeToken == feeToken, "!token"); // dev: gelato not using intended token
        require(gelatoFee <= maxFee, "!fee"); // dev: gelato executor overcharnging for the tx

        // Re-run harvestTrigger() with the gelatoFee passed by the executor to ensure
        // the tx makes economic sense, and that harvestStrategy() is only called when
        // conditions are met. Not checking conditions in the exec function could in
        // theory allow an executor to attempt to run a harvest when checkHarvestStatus()
        // might not be proposing such tx.
        require(StrategyAPI(strategy).harvestTrigger(gelatoFee), "!economic");

        strategy.harvest();

        // Pay Gelato for the service.
        // REVIEW we should discuss reentracy issues
        payKeeper(gelatoFee);

        emit HarvestedByGelato(
            jobId,
            strategyAddress,
            gelatoFeeToken,
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
        require(success, "!transfer");
    }

    /**
    @notice Create Gelato job. The job and resolver address are the same -- the
    Yearn Harvest contract. Updates `jobId`, which we use to log events and
    to manage the job.
    */
    function createKeeperJob() external onlyAuthorized {
        jobId = ops.createTaskNoPrepayment(
            address(this), // `execAddress` - contract where the method to execute resides
            this.harvestStrategy.selector, // `execSelector` - Signature of the method to call
            address(this), // `resolverAddress` - contract that contains the checkHarvestStatus() method
            abi.encodeWithSelector(this.checkHarvestStatus.selector), // call data to check harvest status
            feeToken
        );

        isActive = true;
    }

    /**
    @notice Cancel Gelato job used by yHarvest, which resets `jobId`
    and `isActive` to default values.
    */
    function cancelKeeperJob() external onlyAuthorized {
        ops.cancelTask(jobId);
        delete isActive; // return to default value => false
        delete jobId; // return to default value => TODO
        // REVIEW: isActive = false; ?
    }

    /**
    @notice Set the max fee we allow Gelato to charge for a harvest
    @param _maxFee Max fee we allow Gelato to charge for a harvest.
    */
    function setMaxFee(uint256 _maxFee) external onlyAuthorized {
        maxFee = _maxFee;
    }

    /**
    @notice Used to change `owner`.
    @param _owner The new address to assign as `owner`.
    */
    function setOwner(address _owner) external onlyAuthorized {
        require(_owner != address(0));
        owner = _owner;
    }

    /**
    @notice Used to change `management`.
    @param _management The new address to assign as `management`.
    */
    function setManagement(address _management) external onlyAuthorized {
        require(_management != address(0));
        management = _management;
    }

    // 2-phase commit for a change in governance
    /**
    @notice
    Nominate a new address to use as governance.

    The change does not go into effect immediately. This function sets a
    pending change, and the governance address is not updated until
    the proposed governance address has accepted the responsibility.

    @param _governance The address requested to take over Vault governance.
    */
    function setGovernance(address payable _governance)
        external
        onlyGovernance
    {
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
        governance = pendingGovernance;
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
            amount = IERC20(_token).balanceOf(address(this));
            SafeERC20.safeTransfer(IERC20(_token), governance, amount);
        }
    }

    // enables the contract to receive native crypto (ETH, FTM, AETH, etc)
    receive() external payable {}
}
