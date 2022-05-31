// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

/**
@title Yearn Harvest
@author yearn.finance
@notice Yearn Harvest or yHarvest is a smart contract that leverages Gelato to automate
the harvest of stragegies that have yHarvest assigned as its keeper.
The contract provides the Gelato network of keepers Yearn harvest jobs that
are ready to execute, and it pays Gelato after a succesful harvest.
*/

import {SafeMath} from "@openzeppelin/contracts/math/SafeMath.sol";
import {Address} from "@openzeppelin/contracts/utils/Address.sol";
import {SafeERC20, IERC20} from "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";
import {StrategyAPI} from "@yearnvaults/contracts/BaseStrategy.sol";
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
    uint256 public runMaxTime = 6 hours;

    // `lastRun` keeps track of the time at which a strategy was last harvested, and
    // allows us to determine along with `runMaxTime` whether yHarvest should
    // propose Gelato a strategy to be harvested.
    mapping(address => uint256) internal lastRun;

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
        _initialize(msg.sender, msg.sender, msg.sender);
    }

    // REVIEW: If you don't use clone, there is no need of an _initialize method.
    // When there is a clone, initialize is public and is called after deployment/clone
    function _initialize(
        address _owner,
        address _management,
        address payable _governance
    ) internal {
        owner = _owner;
        management = _management;
        governance = _governance;
    }

    function getLastRun(address strategy) external view returns (uint256) {
        return lastRun[strategy];
    }

    /**
    @notice Used by keepers to check whether a job is ready to run. IMPORTANT: keepers
    are expected to call checkHarvestStatus() as a static, "view" call off-chain.
    @dev The method relies on each strategy to determine whether it's ready for harvest
    (via harvestTrigger()), and attempts a non-state-changing harvest() when the strategy
    trigger returns TRUE.
    Even if the trigger is TRUE and the simulated call to harvest() is succesful, certain
    stragegies may have not needed to be harvested (e.g., Total Assets == 0,
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

        // Declare a strategy object
        StrategyAPI strategy_i;

        // `callCostInWei` is a required input to the `harvestTrigger()` method of the strategy
        // and represents the expected cost to call `harvest()`. Gelato does not currently
        // passes the tx fee it charges to the checker function so we are not able to assess
        // the economic feasibility of the tx here. For now, yHarvest uses a common,
        // fixed cost accross strategies -- `callCostInWei`. A future improvement could
        // include an on-chain estimate.
        //
        // Because of this drawback in the checker function, the executing function --
        // `harvestStrategy()` -- runs `harvestTrigger()` again with the tx fee `gelatoFee`,
        // which IS available in such function. This is not ideal as it adds a cost in the
        // executing function that could be completely avoided if such information would
        // be available in the checker function.

        uint256 callCostInWei = 1e8; // low value so that the trigger focuses on all other conditions

        // Check active strategies and return the first one that is ready to harvest.

        // REVIEW: Two issues of iterating over ALL strategies I can think of:
        // 1) You might run out of gas. If there are enough reverting harvest
        // strategies, the method might consume all the gas.
        //
        // 2) You are forcing an order in the harvest procedure.
        // Not an issue per se, but might be an attack vector
        //
        // I would prefer this logic to live on keepers logic, perhaps offering
        // this helper method but separated in two:
        // a) getAllHarvestableStrategies()
        // b) CheckIfHarvestable()
        //
        // On the other hand, we know that keepers check in a fork before sending
        // to avoid reverts, but I don't know if gelato offers that.
        //
        for (uint256 i = 0; i < strategies.length; i++) {
            // When `minReportDelay` is zero at the strategy level, it's possible that
            // harvestTrigger() could return TRUE. If that were the case, checkHarvestStatus() could
            // find itself returning the same strategy, preventing other strategies that
            // need to be harvest from doing so.
            // We must track, then, when a strategy was last harvested to avoid this
            // situation. We require that a strategy is not run more often than `runMaxTime`.
            if (now.sub(lastRun[strategies[i]]) < runMaxTime) continue;

            // Define `strategy_i`
            strategy_i = StrategyAPI(strategies[i]);

            // To enable automatic harvest() calls, a strategy must have the Yearn Harvest
            // contract as the keeper.
            if (strategy_i.keeper() != address(this)) continue;

            // Gelato does not currently accept input parameters in the checkHarvestStatus()
            // method, but harvestTrigger() requires one. For now we pass `callCostInWei`, which
            // is a constant used accross all strategies.
            // Note, however, that `gelatoFee` in the `harvestStrategy()` method is used to
            // run the `harvestTrigger()` method again to ensure the tx makes economic
            // sense. Running the trigger in that method is not ideal, however, because it's
            // not gas-efficient.
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
    @param strategy Strategy to harvest
    */
    function harvestStrategy(address strategy) public onlyKeepers {
        require(isActive, "!active");
        require(now.sub(lastRun[strategy]) > runMaxTime, "!time");

        // `gelatoFee` and `gelatoFeeToken` are state variables in the gelato contract that
        // are temporarily modified by the executors before executing the payload. They are
        // reverted to default values when the gelato contract exec() method wraps up.
        (uint256 gelatoFee, address gelatoFeeToken) = ops.getFeeDetails();

        require(gelatoFeeToken == feeToken, "!token"); // dev: gelato not using intended token
        require(gelatoFee <= maxFee, "!fee"); // dev: gelato executor overcharnging for the tx

        // REVIEW: To avoid this variable you can read lastRun from:
        // vault.strategies(strategy)
        lastRun[strategy] = now;

        // The checker method `checkHarvestStatus()` does not currently factor in whether it
        // makes economic sense to harvest (e.g., profit > hatvest tx cost). This is because
        // we don't have access to `gelatoFee` in that method.
        // require(StrategyAPI(strategy).harvestTrigger(gelatoFee), "!economic");

        StrategyAPI(strategy).harvest();

        // Pay Gelato for the service.
        // REVIEW we should discuss reentracy issues
        payKeeper(gelatoFee);

        emit HarvestedByGelato(jobId, strategy, gelatoFeeToken, gelatoFee);
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
    function setGovernance(address payable _governance) external onlyGovernance {
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

    // REVIEW: Sometimes we add a sweepETH as well.

    // enables the contract to receive native crypto (ETH, FTM, AETH, etc)
    receive() external payable {}
}
