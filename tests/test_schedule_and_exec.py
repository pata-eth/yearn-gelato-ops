from brownie import convert, reverts, chain, accounts


def test_launch_strategy_monitor(
    yHarvest,
    gelato,
    native,
):

    tx = yHarvest.initiateStrategyMonitor()

    # inspect events with job information
    tx.info()

    assert yHarvest.address == tx.events[0][0]["execAddress"]
    assert yHarvest.address == tx.events[0][0]["resolverAddress"]
    assert yHarvest.address == tx.events[0][0]["taskCreator"]

    assert yHarvest.jobIds(yHarvest) == tx.events[0][0]["taskId"]

    assert (
        tx.events[0][0]["useTaskTreasuryFunds"] == False
    ), "We shouldn't be using Gelato's treasury"

    assert tx.events[0][0]["feeToken"] == native

    JobId = gelato.getTaskIdsByUser(yHarvest)

    assert JobId[0] == yHarvest.jobIds(yHarvest)


def test_strategy_job_schedule(
    yHarvest,
    gelato,
    strategy,
    owner,
    strategist_ms,
    gov,
    gelatoFee,
    ftm_amount,
    crv,
    strategy_not_onboarded,
    native,
):
    tx = yHarvest.initiateStrategyMonitor()

    assert strategy.keeper() == yHarvest

    resolverHash = tx.events[0][0]["resolverHash"]

    [canExec, execData] = yHarvest.checkNewStrategies.call({"from": accounts[0]})

    assert canExec, "strategy not detected"

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress

    with reverts():
        gelato.exec(
            gelatoFee,
            native,
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            True,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": owner},
        )

    with reverts():
        gelato.exec(
            gelatoFee,
            native,
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            True,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": strategist_ms},
        )

    with reverts():
        gelato.exec(
            gelatoFee,
            native,
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            True,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": gov},
        )

    with reverts():
        gelato.exec(
            gelatoFee,
            native,
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            True,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": accounts[0]},
        )

    # Gelato executor attempts to charge above maxFee
    with reverts():
        gelato.exec(
            100 * 10**18,
            native,
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            True,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": gelato.gelato()},
        )

    # Gelato executor attempts to charge with a wrong token. The task wouldn't be found
    # as the feeToken is part of the identifier.
    with reverts():
        gelato.exec(
            gelatoFee,
            crv,
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            True,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": gelato.gelato()},
        )

    # create a new Gelato job for the strategy just onboarded to yHarvest
    tx = gelato.exec(
        gelatoFee,
        native,
        yHarvest.address,
        False,  # do not use Gelato Treasury for payment
        True,
        resolverHash,
        yHarvest.address,
        execData,
        {"from": gelato.gelato()},
    )

    # Verify that we paid Gelato
    assert yHarvest.balance() + gelatoFee == ftm_amount

    jobIds = gelato.getTaskIdsByUser(yHarvest)

    assert yHarvest.jobIds(strategy) in jobIds, "Job not created"

    resolverHash = tx.events[0][0]["resolverHash"]

    [canExec, execData] = yHarvest.checkHarvestStatus.call(
        strategy, {"from": accounts[0]}
    )

    assert canExec, "Strategy not ready to harvest"

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress
    assert strategy.keeper() == yHarvest

    tx = gelato.exec(
        gelatoFee,
        native,
        yHarvest.address,
        False,  # do not use Gelato Treasury for payment
        True,
        resolverHash,
        yHarvest.address,
        execData,
        {"from": gelato.gelato()},
    )

    # Verify that we paid Gelato
    assert yHarvest.balance() + gelatoFee * 2 == ftm_amount

    # revert action
    chain.undo()

    # Yearn Harvest must be set as the strategy's keeper. Otherwise it'll revert.
    strategy.setKeeper(accounts[0], {"from": owner})

    with reverts():
        gelato.exec(
            gelatoFee,
            native,
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            True,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": gelato.gelato()},
        )

    # If the the strategy's keeper is not yHarvest, then it stops
    # showing up in the resolver
    [canExec, execData] = yHarvest.checkHarvestStatus.call(
        strategy, {"from": accounts[0]}
    )

    assert convert.to_string(execData) == "Strategy no longer automated by yHarvest"
    assert not canExec

    [canExec, execData] = yHarvest.checkHarvestStatus.call(
        strategy_not_onboarded, {"from": accounts[0]}
    )

    assert convert.to_string(execData) == "Strategy was never onboarded to yHarvest"
    assert not canExec
