from brownie import ZERO_ADDRESS, reverts, accounts


def test_strategy_is_active(strategy, lens, yGO):

    # Get a list of active strategies in production
    strategies = lens.assetsStrategiesAddresses()

    assert strategy in strategies, "Strategy is not active in production"

    # To onboard strategies to the yGO job, they must assign its keeper to the
    # yGO
    assert (
        strategy.keeper() == yGO
    ), "Yearn Gelato Ops is not the strategy's keeper"


def test_initial_params(
    yGO,
    owner,
    gelato,
):
    jobIds = gelato.getTaskIdsByUser(yGO)
    assert len(jobIds) == 0, "Job ID must be empty"

    assert yGO.owner() == owner
    assert yGO.governance() == owner
    assert yGO.keeper() == gelato
    assert yGO.pendingGovernance() == ZERO_ADDRESS


def test_methods(yGO, native, owner, gov, usdc, gelato, job_types):

    # Revert if we try to cancel a non-existent job
    with reverts("Ops.cancelTask: Task not found"):
        yGO.cancelJob(job_types.MONITOR, yGO.address, {"from": owner})

    with reverts("!authorized"):
        yGO.cancelJob(job_types.MONITOR, yGO.address, {"from": accounts[0]})

    with reverts("!authorized"):
        yGO.cancelJob(job_types.TEND, yGO.address, {"from": accounts[0]})

    with reverts("!keeper"):
        yGO.createJob(job_types.MONITOR, yGO.address, {"from": accounts[0]})

    with reverts("!authorized"):
        yGO.acceptGovernance({"from": accounts[0]})

    with reverts("!authorized"):
        yGO.setKeeper(owner, {"from": accounts[0]})

    with reverts("!governance"):
        yGO.sweep(native, {"from": gov})

    with reverts("!authorized"):
        yGO.setMaxFee(10 * 10**18, {"from": accounts[0]})

    # Transfer zero balance
    yGO.sweep(native, {"from": owner})

    # Transfer any token. Even if not defined as a state
    # variable in the contract
    yGO.sweep(usdc, {"from": owner})

    yGO.createJob(job_types.MONITOR, yGO.address)

    # Can't create the same job twice
    with reverts():
        yGO.createJob(job_types.MONITOR, yGO.address)

    yGO.setKeeper(owner)
    assert yGO.keeper() == owner.address
