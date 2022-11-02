from brownie import Contract, accounts


def test_all_strategies(
    yGO,
    gelato,
    lens,
    gov,
    baseFee,
    gelatoFee,
    native,
    new_strat_module_data,
):

    # Get a list of active strategies in production
    strategies = lens.assetsStrategiesAddresses()

    # Create Gelato job
    yGO.initiateStrategyMonitor()

    # Check that the job IDs match
    assert yGO.jobIds(yGO)[0] == gelato.getTaskIdsByUser(yGO)[0]

    # Assign the Yearn Gelato Ops as the keeper, check the resolver,
    # and execute when strat is harvestable
    for i in range(0, len(strategies)):
        strat_i = Contract(strategies[i])
        assets_i = strat_i.estimatedTotalAssets()

        if assets_i > 0:
            strat_i.setKeeper(yGO, {"from": gov})
            assert strat_i.keeper() == yGO

    # Simulate Gelato executors and create a job for each strategy
    [canExec, execData] = yGO.checkNewStrategies.call({"from": accounts[0]})

    while canExec:
        gelato.exec(
            yGO.address,
            yGO.address,
            execData,
            new_strat_module_data,
            gelatoFee,
            native,
            False,  # do not use Gelato Treasury for payment
            True,
            {"from": gelato.gelato()},
        )

        [canExec, execData] = yGO.checkNewStrategies.call(
            {"from": accounts[0]}
        )

    jobIds = gelato.getTaskIdsByUser(yGO)

    # Check harvest conditions and attempt to harvest when needed
    for i in range(0, len(strategies)):
        strat_i = Contract(strategies[i])
        assets_i = strat_i.estimatedTotalAssets()
        if assets_i > 0:
            assert yGO.jobIds(strategies[i])[0] in jobIds, "Job not created"

            # Check if there are harvest jobs to run
            [canExec, execData] = yGO.checkHarvestTrigger.call(
                strategies[i], {"from": gelato.gelato()}
            )
            assert strat_i.harvestTrigger(baseFee) == canExec, "no match"

            if not canExec:
                continue

            func_encoded_w_selector = yGO.checkHarvestTrigger.encode_input(
                strategies[i]
            )
            selector = func_encoded_w_selector[2:10] + "0" * 56
            input_args = func_encoded_w_selector[10:]
            moduleData_args = (
                "0x" + "0" * 24 + yGO.address[2:] + selector + input_args
            )
            moduleData = ([0], [moduleData_args])

            tx_i = gelato.exec(
                yGO.address,
                yGO.address,
                execData,
                moduleData,
                gelatoFee,
                native,
                False,  # do not use Gelato Treasury for payment
                False,  # do not revert if the tx fails
                {"from": gelato.gelato()},
            )

            if "HarvestByGelato" in tx_i.events:
                print(
                    f"\033[92mSuccess! {strat_i.name()} ({strategies[i]}) "
                    "was harvested.\033[0m\n"
                )
            else:
                print(
                    f"\033[91mFailed! {strat_i.name()} ({strategies[i]}) "
                    "reverts.\033[0m\n"
                )
