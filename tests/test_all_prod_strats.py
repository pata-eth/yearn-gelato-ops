from brownie import Contract, accounts


def test_all_strategies(
    yHarvest,
    gelato,
    aggregator,
    gov,
    baseFee,
    gelatoFee,
    native,
):

    # Get a list of active strategies in production
    strategies = aggregator.assetsStrategiesAddresses()

    # Create Gelato job
    tx = yHarvest.initiateStrategyMonitor()

    resolverHash = tx.events[0][0]["resolverHash"]

    # Assign the Yearn Harvest as the keeper, check the resolver,
    # and execute when strat is harvestable
    for i in range(0, len(strategies)):
        strat_i = Contract(strategies[i])
        assets_i = strat_i.estimatedTotalAssets()
        # print(f"Strategy {strategies[i]} has {strat_i.estimatedTotalAssets()/10**18:_} in assets.\n")
        if assets_i > 0:
            strat_i.setKeeper(yHarvest, {"from": gov})
            assert strat_i.keeper() == yHarvest

    # Simulate Gelato executors and create a job for each strategy
    [canExec, execData] = yHarvest.checkNewStrategies.call({"from": accounts[0]})

    while canExec:
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

        [canExec, execData] = yHarvest.checkNewStrategies.call({"from": accounts[0]})

    jobIds = gelato.getTaskIdsByUser(yHarvest)

    # Check harvest conditions and attempt to harvest when needed
    for i in range(0, len(strategies)):
        strat_i = Contract(strategies[i])
        assets_i = strat_i.estimatedTotalAssets()
        if assets_i > 0:
            assert yHarvest.jobIds(strategies[i]) in jobIds, "Job not created"

            # Check if there are harvest jobs to run
            [canExec, execData] = yHarvest.checkHarvestStatus.call(
                strategies[i], {"from": gelato.gelato()}
            )
            assert strat_i.harvestTrigger(baseFee) == canExec, "no match"

            if not canExec:
                continue

            tx_i = gelato.exec(
                gelatoFee,
                native,
                yHarvest.address,
                False,  # do not use Gelato Treasury for payment
                False,  # do not revert if the tx fails so that the test does not fail
                gelato.getResolverHash(
                    yHarvest.address,
                    yHarvest.checkHarvestStatus.encode_input(strategies[i]),
                ),
                yHarvest.address,
                execData,
                {"from": gelato.gelato()},
            )

            if "HarvestedByGelato" in tx_i.events:
                print(
                    f"\033[92mSuccess! {strat_i.name()} ({strategies[i]}) was harvested.\033[0m\n"
                )
            else:
                print(
                    f"\033[91mFailed! {strat_i.name()} ({strategies[i]}) reverts.\033[0m\n"
                )
