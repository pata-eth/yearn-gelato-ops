from brownie import ZERO_ADDRESS, reverts, accounts


def test_strategy_is_active(strategy, lens, yHarvest):

    # Get a list of active strategies in production
    strategies = lens.assetsStrategiesAddresses()

    assert strategy in strategies, "Strategy is not active in production"

    # To onboard strategies to the yHarvest job, they must assign its keeper to the yHarvest
    assert strategy.keeper() == yHarvest, "Yearn Harvest is not the strategy's keeper"


def test_initial_params(
    yHarvest,
    owner,
):
    assert int(yHarvest.jobIds(yHarvest.address)[0].hex()) == 0, "Job ID must be empty"

    assert yHarvest.owner() == owner
    assert yHarvest.governance() == owner
    assert yHarvest.pendingGovernance() == ZERO_ADDRESS


def test_methods(
    yHarvest,
    native,
    owner,
    gov,
    crv,
    gelato,
):

    # Revert if we try to cancel a non-existent job
    with reverts():
        yHarvest.cancelJob(yHarvest, True, {"from": owner})

    with reverts("!authorized"):
        yHarvest.cancelJob(yHarvest, True, {"from": accounts[0]})

    with reverts("!authorized"):
        yHarvest.cancelJob(yHarvest, False, {"from": accounts[0]})

    with reverts("!authorized"):
        yHarvest.initiateStrategyMonitor({"from": accounts[0]})

    with reverts("!authorized"):
        yHarvest.initiateStrategyMonitor({"from": gelato})

    with reverts("!authorized"):
        yHarvest.acceptGovernance({"from": accounts[0]})

    with reverts("!governance"):
        yHarvest.sweep(native, {"from": gov})

    with reverts("!authorized"):
        yHarvest.setMaxFee(10 * 10**18, {"from": accounts[0]})

    # Transfer zero balance
    yHarvest.sweep(native, {"from": owner})

    # Transfer any token. Even if not defined as a state variable in the contract
    yHarvest.sweep(crv, {"from": owner})

    yHarvest.initiateStrategyMonitor()

    # Can't create the same job twice
    with reverts():
        yHarvest.initiateStrategyMonitor()
