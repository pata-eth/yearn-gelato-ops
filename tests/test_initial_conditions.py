from brownie import ZERO_ADDRESS, reverts, accounts


def test_strategy_is_active(strategy, aggregator, yHarvest):

    # Get a list of active strategies in production
    strategies = aggregator.assetsStrategiesAddresses()

    assert strategy in strategies, "Strategy is not active in production"

    # To onboard strategies to the yHarvest job, they must assign its keeper to the yHarvest
    assert strategy.keeper() == yHarvest, "Yearn Harvest is not the strategy's keeper"


def test_initial_params(
    yHarvest,
    owner,
    strategist_ms,
    gov,
):
    assert int(yHarvest.jobIds(yHarvest.address).hex()) == 0, "Job ID must be empty"

    assert yHarvest.owner() == owner
    assert yHarvest.governance() == gov
    assert yHarvest.management() == strategist_ms
    assert yHarvest.pendingGovernance() == ZERO_ADDRESS


def test_methods(
    yHarvest,
    native,
    owner,
    gov,
    crv,
):

    # Revert if we try to cancel a non-existent job
    with reverts():
        yHarvest.cancelJob(yHarvest, {"from": owner})

    with reverts("!authorized"):
        yHarvest.cancelJob(yHarvest, {"from": accounts[0]})

    with reverts("!authorized"):
        yHarvest.initiateStrategyMonitor({"from": accounts[0]})

    with reverts("!authorized"):
        yHarvest.acceptGovernance({"from": accounts[0]})

    with reverts("!governance"):
        yHarvest.sweep(native, {"from": owner})

    with reverts("!authorized"):
        yHarvest.setMaxFee(10 * 10**18, {"from": accounts[0]})

    # Transfer zero balance
    yHarvest.sweep(native, {"from": gov})

    # Transfer any token. Even if not defined as a state variable in the contract
    yHarvest.sweep(crv, {"from": gov})

    yHarvest.initiateStrategyMonitor()

    # Can't create the same job twice
    with reverts():
        yHarvest.initiateStrategyMonitor()
