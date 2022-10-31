from brownie import convert, reverts, chain, accounts


def test_launch_strategy_monitor(
    yGO,
    gelato,
    native,
):

    tx = yGO.initiateStrategyMonitor()

    # inspect events with job information
    tx.info()

    assert yGO.jobIds(yGO)[0] == gelato.getTaskIdsByUser(yGO)[0]

    JobId = gelato.getTaskIdsByUser(yGO)

    assert JobId[0] == yGO.jobIds(yGO)[0]


def test_strategy_job_schedule(
    yGO,
    gelato,
    strategy,
    owner,
    gov,
    gelatoFee,
    amount,
    usdc,
    strategy_not_onboarded,
    native,
    sms,
):
    yGO.initiateStrategyMonitor()

    assert strategy.keeper() == yGO

    [canExec, execData] = yGO.checkNewStrategies.call({"from": accounts[0]})

    assert canExec, "strategy not detected"

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress

    with reverts("Gelatofied: Only gelato"):
        gelato.exec(
            yGO.address,
            yGO.address,
            execData,
            ([0], [yGO.checkNewStrategies.encode_input()]),
            gelatoFee,
            native,
            False,  # do not use Gelato Treasury for payment
            True,
            {"from": owner},
        )

    with reverts("Gelatofied: Only gelato"):
        gelato.exec(
            yGO.address,
            yGO.address,
            execData,
            ([0], [yGO.checkNewStrategies.encode_input()]),
            gelatoFee,
            native,
            False,  # do not use Gelato Treasury for payment
            True,
            {"from": gov},
        )

    with reverts("Gelatofied: Only gelato"):
        gelato.exec(
            yGO.address,
            yGO.address,
            execData,
            ([0], [yGO.checkNewStrategies.encode_input()]),
            gelatoFee,
            native,
            False,  # do not use Gelato Treasury for payment
            True,
            {"from": accounts[0]},
        )

    # Gelato executor attempts to charge above maxFee
    with reverts("Ops.exec: !fee"):
        gelato.exec(
            yGO.address,
            yGO.address,
            execData,
            ([0], [yGO.checkNewStrategies.encode_input()]),
            10**17,
            native,
            False,  # do not use Gelato Treasury for payment
            True,
            {"from": gelato.gelato()},
        )

    # Gelato executor attempts to charge with a wrong token. The task wouldn't
    # be found as the feeToken is part of the identifier.
    with reverts("Ops.exec: Task not found"):
        gelato.exec(
            yGO.address,
            yGO.address,
            execData,
            ([0], [yGO.checkNewStrategies.encode_input()]),
            gelatoFee,
            usdc,
            False,  # do not use Gelato Treasury for payment
            True,
            {"from": gelato.gelato()},
        )

    # create a new Gelato job for the strategy just onboarded to yGO
    gelato.exec(
        yGO.address,
        yGO.address,
        execData,
        ([0], [yGO.checkNewStrategies.encode_input()]),
        gelatoFee,
        native,
        False,  # do not use Gelato Treasury for payment
        True,
        {"from": gelato.gelato()},
    )

    # Verify that we paid Gelato
    assert yGO.balance() + gelatoFee == amount

    jobIds = gelato.getTaskIdsByUser(yGO)

    assert yGO.jobIds(strategy)[0] in jobIds, "Job not created"

    [canExec, execData] = yGO.checkHarvestTrigger.call(
        strategy, {"from": accounts[0]}
    )

    assert canExec, "Strategy not ready to harvest"

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress
    assert strategy.keeper() == yGO

    gelato.exec(
        yGO.address,
        yGO.address,
        execData,
        ([0], [yGO.checkHarvestTrigger.encode_input(stratAddress)]),
        gelatoFee,
        native,
        False,  # do not use Gelato Treasury for payment
        True,
        {"from": gelato.gelato()},
    )

    # Verify that we paid Gelato
    assert yGO.balance() + gelatoFee * 2 == amount

    # revert action
    chain.undo()

    # Yearn Gelato Ops must be set as the strategy's keeper. Otherwise it'll
    # revert.
    strategy.setKeeper(accounts[0], {"from": sms})

    with reverts("Ops.exec: !authorized"):
        gelato.exec(
            yGO.address,
            yGO.address,
            execData,
            ([0], [yGO.checkHarvestTrigger.encode_input(stratAddress)]),
            gelatoFee,
            native,
            False,  # do not use Gelato Treasury for payment
            True,
            {"from": gelato.gelato()},
        )

    # If the strategy's keeper is not yGO, then it stops
    # showing up in the resolver
    [canExec, execData] = yGO.checkHarvestTrigger.call(
        strategy, {"from": accounts[0]}
    )

    assert (
        convert.to_string(execData)
        == "Strategy no longer automated by yGO for harvest operations"
    )
    assert not canExec

    [canExec, execData] = yGO.checkHarvestTrigger.call(
        strategy_not_onboarded, {"from": accounts[0]}
    )

    assert (
        convert.to_string(execData)
        == "Strategy was never onboarded to yGO for harvest operations"
    )
    assert not canExec


def test_harvest_job_cancellation(
    yGO,
    gelato,
    strategy,
    owner,
    gelatoFee,
    native,
):
    yGO.initiateStrategyMonitor()

    [_, execData] = yGO.checkNewStrategies.call({"from": accounts[0]})

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress

    # create a new Gelato job for the strategy just onboarded to yGO
    gelato.exec(
        yGO.address,
        yGO.address,
        execData,
        ([0], [yGO.checkNewStrategies.encode_input()]),
        gelatoFee,
        native,
        False,  # do not use Gelato Treasury for payment
        True,
        {"from": gelato.gelato()},
    )

    [_, execData] = yGO.checkHarvestTrigger.call(
        strategy, {"from": accounts[0]}
    )

    gelato.exec(
        yGO.address,
        yGO.address,
        execData,
        ([0], [yGO.checkHarvestTrigger.encode_input(stratAddress)]),
        gelatoFee,
        native,
        False,  # do not use Gelato Treasury for payment
        True,
        {"from": gelato.gelato()},
    )

    yGO.cancelJob(strategy, True, {"from": owner})

    [canExec, execData] = yGO.checkNewStrategies.call({"from": accounts[0]})

    assert (
        canExec is False
    ), "Cancelled jobs should not be automatically picked up."
