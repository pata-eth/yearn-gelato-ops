from brownie import ZERO_ADDRESS, reverts, accounts


def test_strategy_is_active(strategy, aggregator, yHarvest):

    # Get a list of active strategies in production
    strategies = aggregator.assetsStrategiesAddresses()

    assert strategy in strategies, "Strategy is not active in production"

    # To onboard strategies to the yHarvest job, they must assign its keeper to the yHarvest
    assert (
        strategy.keeper() == yHarvest
    ), "Yearn Harvest is not the strategy's keeper"


def test_initial_params(
    yHarvest,
    owner,
    strategist_ms,
    gov,
):
    assert not yHarvest.isActive(), "Harvest is active"
    assert int(yHarvest.jobId().hex()) == 0, "Job ID must be empty"

    assert yHarvest.owner() == owner
    assert yHarvest.governance() == gov
    assert yHarvest.management() == strategist_ms
    assert yHarvest.pendingGovernance() == ZERO_ADDRESS


def test_methods(
    yHarvest,
    native,
    owner,
    gelato,
    gov,
    crv,
):

    # checkHarvestStatus() is meant to be a call and not a tx. Confirm that
    # only gelato can run thsi method.
    with reverts():
        yHarvest.checkHarvestStatus.call({"from": accounts[0]})

    [canExec, payload] = yHarvest.checkHarvestStatus.call({"from": gelato.gelato()})

    assert (
        not yHarvest.isActive() and not canExec
    ), "canExec must return False when inactive"

    assert payload.hex() == "", "Payload must have been empty"

    # Revert is we try to cancel a non-existent job
    with reverts():
        yHarvest.cancelKeeperJob({"from": owner})

    with reverts("!authorized"):
        yHarvest.cancelKeeperJob({"from": accounts[0]})

    with reverts("!authorized"):
        yHarvest.createKeeperJob({"from": accounts[0]})

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

    yHarvest.createKeeperJob()

    # Can't create the same job twice
    with reverts():
        yHarvest.createKeeperJob()
