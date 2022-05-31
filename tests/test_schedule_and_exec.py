from brownie import convert, reverts, chain, accounts


def test_schedule_job_native(
    yHarvest,
    gelato,
):

    tx = yHarvest.createKeeperJob()

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

    assert JobId[0] == yHarvest.jobId()


def test_checker(
    yHarvest,
    gelato,
    strategy,
    owner,
    strategist_ms,
    baseFee,
    gelatoFee,
    crv,
    gov,
    ftm_amount,
    revertOnFailure,
):
    tx = yHarvest.createKeeperJob()

    resolverHash = tx.events[0][0]["resolverHash"]

    isHarvestable = strategy.harvestTrigger(baseFee)

    [canExec, execData] = yHarvest.checkHarvestStatus.call({"from": gelato.gelato()})

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress
    assert isHarvestable and canExec

    with reverts():
        gelato.exec(
            gelatoFee,
            yHarvest.feeToken(),
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            revertOnFailure,
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
            revertOnFailure,
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
            revertOnFailure,
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
            revertOnFailure,
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
            revertOnFailure,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": gelato.gelato()},
        )

    # Gelato executor attempts to charge with a wrong token
    with reverts():
        gelato.exec(
            gelatoFee,
            crv,
            yHarvest.address,
            False,  # do not use Gelato Treasury for payment
            revertOnFailure,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": gelato.gelato()},
        )

    # We first harvest the strategy to make sure the tx goes ok.
    tx_direct = strategy.harvest({"from": owner})

    # revert action
    chain.undo()

    # Harvest again via yHarvest
    tx_gelato = gelato.exec(
        gelatoFee,
        yHarvest.feeToken(),
        yHarvest.address,
        False,  # do not use Gelato Treasury for payment
        revertOnFailure,
        resolverHash,
        yHarvest.address,
        execData,
        {"from": gelato.gelato()},
    )

    # Verify that we paid Gelato
    assert yHarvest.balance() + gelatoFee == ftm_amount

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
            revertOnFailure,
            resolverHash,
            yHarvest.address,
            execData,
            {"from": gelato.gelato()},
        )

    # If the the strategy's keeper is not yHarvest, then it stops
    # showing up in the resolver
    [canExec, execData] = yHarvest.checkHarvestStatus.call({"from": gelato.gelato()})

    assert not canExec
