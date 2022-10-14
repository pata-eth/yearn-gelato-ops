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

    assert yHarvest.jobIds(yHarvest)[0] == tx.events[0][0]["taskId"]

    assert (
        tx.events[0][0]["useTaskTreasuryFunds"] == False
    ), "We shouldn't be using Gelato's treasury"

    assert tx.events[0][0]["feeToken"] == native

    JobId = gelato.getTaskIdsByUser(yHarvest)

    assert JobId[0] == yHarvest.jobIds(yHarvest)[0]


def test_strategy_job_schedule(
    yHarvest,
    gelato,
    strategy,
    owner,
    gov,
    gelatoFee,
    amount,
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
    assert yHarvest.balance() + gelatoFee == amount

    jobIds = gelato.getTaskIdsByUser(yHarvest)

    assert yHarvest.jobIds(strategy)[0] in jobIds, "Job not created"

    resolverHash = tx.events[0][0]["resolverHash"]

    [canExec, execData] = yHarvest.checkHarvestTrigger.call(
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
    assert yHarvest.balance() + gelatoFee * 2 == amount

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
    [canExec, execData] = yHarvest.checkHarvestTrigger.call(
        strategy, {"from": accounts[0]}
    )

    assert convert.to_string(execData) == "Strategy no longer automated by yHarvest for harvest operations"
    assert not canExec

    [canExec, execData] = yHarvest.checkHarvestTrigger.call(
        strategy_not_onboarded, {"from": accounts[0]}
    )

    assert convert.to_string(execData) == "Strategy was never onboarded to yHarvest for harvest operations"
    assert not canExec


def test_harvest_job_cancellation(
    yHarvest,
    gelato,
    strategy,
    owner,
    gov,
    gelatoFee,
    amount,
    crv,
    strategy_not_onboarded,
    native,
):
    tx = yHarvest.initiateStrategyMonitor()

    resolverHash = tx.events[0][0]["resolverHash"]

    [_, execData] = yHarvest.checkNewStrategies.call({"from": accounts[0]})

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress

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

    resolverHash = tx.events[0][0]["resolverHash"]

    strategy.setForceHarvestTriggerOnce(True, {"from": owner})

    [_, execData] = yHarvest.checkHarvestTrigger.call(
        strategy, {"from": accounts[0]}
    )

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

    yHarvest.cancelJob(strategy, True, {'from': owner})

    strategy.setForceHarvestTriggerOnce(True, {"from": owner})

    [canExec, execData] = yHarvest.checkNewStrategies.call({"from": accounts[0]})

    assert canExec is False
