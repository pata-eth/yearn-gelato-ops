from brownie import Contract, accounts


def test_all_strategies(
    yGO, gelato, lens, gov, baseFee, gelatoFee, native, job_types
):

    # Get a list of active strategies in production
    strategies = lens.assetsStrategiesAddresses()

    # Create Strategy Monitor job
    tx = yGO.createJob(job_types.MONITOR, yGO.address)

    # Check that the job IDs match
    jobId = yGO.getJobId(job_types.MONITOR, yGO.address)
    assert jobId == tx.events["JobCreated"]["jobId"]
    assert jobId in gelato.getTaskIdsByUser(yGO)

    jobId_gelato = gelato.getTaskId(
        yGO.address,
        yGO.address,
        yGO.signatures["createHarvestJob"],
        yGO.getModuleData(job_types.MONITOR, yGO.address),
        native,
    )

    assert jobId == jobId_gelato

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

    module_data = yGO.getModuleData(job_types.MONITOR, yGO.address)

    while canExec:
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

        [canExec, execData] = yGO.checkNewStrategies.call(
            {"from": accounts[0]}
        )

    jobIds = gelato.getTaskIdsByUser(yGO)

    # Check harvest conditions and attempt to harvest when needed
    for i in range(0, len(strategies)):
        strat_i = Contract(strategies[i])
        assets_i = strat_i.estimatedTotalAssets()
        if assets_i > 0:
            assert (
                yGO.getJobId(job_types.HARVEST, strategies[i]) in jobIds
            ), "Job not created"

            # Check if there are harvest jobs to run
            [canExec, execData] = yGO.checkHarvestTrigger.call(
                strategies[i], {"from": gelato.gelato()}
            )
            assert strat_i.harvestTrigger(baseFee) == canExec, "no match"

            if not canExec:
                continue

            tx_i = gelato.exec(
                yGO.address,
                yGO.address,
                execData,
                yGO.getModuleData(job_types.HARVEST, strategies[i]),
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
