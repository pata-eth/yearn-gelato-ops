from brownie import convert, reverts, chain, accounts


def test_schedule_job_native(
    yHarvest,
    gelato,
):

    tx = yHarvest.initiateStrategyMonitor()

    # inspect events with job information
    tx.info()

    assert yHarvest.address == tx.events[0][0]["execAddress"]
    assert yHarvest.address == tx.events[0][0]["resolverAddress"]
    assert yHarvest.address == tx.events[0][0]["taskCreator"]

    assert yHarvest.jobId() == tx.events[0][0]["taskId"]

    assert (
        tx.events[0][0]["useTaskTreasuryFunds"] == False
    ), "We shouldn't be using Gelato's treasury"

    assert yHarvest.feeToken() == tx.events[0][0]["feeToken"]

    JobId = gelato.getTaskIdsByUser(yHarvest)

    assert JobId[0] == yHarvest.jobIds(yHarvest)


def test_job_creations(
    yHarvest,
    gelato,
    strategy,
    owner,
    strategist_ms,
    gov,
    gelatoFee,
    ftm_amount,
    crv,
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
            yHarvest.feeToken(),
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
            yHarvest.feeToken(),
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
            yHarvest.feeToken(),
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
            yHarvest.feeToken(),
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
            yHarvest.feeToken(),
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
        yHarvest.feeToken(),
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

    assert 1 == 2

    resolverHash = tx.events[0][0]["resolverHash"]

    [canExec, execData] = yHarvest.checkHarvestStatus.call(
        strategy, {"from": accounts[0]}
    )

    assert canExec, "Strategy not ready for harvest"

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress
    assert strategy.keeper() == yHarvest

    tx = gelato.exec(
        gelatoFee,
        yHarvest.feeToken(),
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
            yHarvest.feeToken(),
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
        strategy, {"from": gelato.gelato()}
    )

    assert not canExec
