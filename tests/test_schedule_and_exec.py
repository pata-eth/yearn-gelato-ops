from brownie import convert, reverts, chain, accounts


def test_strategy_job_schedule(
    yGO,
    gelato,
    job_types,
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
    # Create strategy monitor job
    yGO.createJob(job_types.MONITOR, yGO.address)

    assert strategy.keeper() == yGO

    [canExec, execData] = yGO.checkNewStrategies.call({"from": accounts[0]})

    assert canExec, "strategy not detected"

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress

    module_data = yGO.getModuleData(job_types.MONITOR, yGO.address)

    with reverts("Gelatofied: Only gelato"):
        gelato.exec(
            yGO.address,
            yGO.address,
            execData,
            module_data,
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
            module_data,
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
            module_data,
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
            module_data,
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
            module_data,
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
        module_data,
        gelatoFee,
        native,
        False,  # do not use Gelato Treasury for payment
        True,
        {"from": gelato.gelato()},
    )

    # Verify that we paid Gelato
    assert yGO.balance() + gelatoFee == amount

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
        yGO.getModuleData(job_types.HARVEST, stratAddress),
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
            yGO.getModuleData(job_types.HARVEST, stratAddress),
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
        == "Strategy not onboarded to yGO for harvest operations"
    )
    assert not canExec

    [canExec, execData] = yGO.checkHarvestTrigger.call(
        strategy_not_onboarded, {"from": accounts[0]}
    )

    assert (
        convert.to_string(execData)
        == "Strategy not onboarded to yGO for harvest operations"
    )
    assert not canExec


def test_harvest_job_cancellation(
    yGO,
    gelato,
    strategy,
    owner,
    gelatoFee,
    native,
    job_types,
):
    # Create strategy monitor job
    yGO.createJob(job_types.MONITOR, yGO.address)

    [_, execData] = yGO.checkNewStrategies.call({"from": accounts[0]})

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    assert strategy.address == stratAddress

    # create a new Gelato job for the strategy just onboarded to yGO
    gelato.exec(
        yGO.address,
        yGO.address,
        execData,
        yGO.getModuleData(job_types.MONITOR, yGO.address),
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
        yGO.getModuleData(job_types.HARVEST, strategy.address),
        gelatoFee,
        native,
        False,  # do not use Gelato Treasury for payment
        True,
        {"from": gelato.gelato()},
    )

    with reverts("!removed"):
        yGO.cancelJob(job_types.HARVEST, strategy, {"from": owner})

    strategy.setKeeper(owner)

    yGO.cancelJob(job_types.HARVEST, strategy, {"from": owner})

    [canExec, execData] = yGO.checkNewStrategies.call({"from": accounts[0]})

    assert (
        canExec is False
    ), "Cancelled jobs should not be automatically picked up."
