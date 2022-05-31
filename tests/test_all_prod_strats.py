from brownie import Contract, convert


def test_all_strategies(
    yHarvest,
    gelato,
    aggregator,
    gov,
    baseFee,
    gelatoFee,
    revertOnFailure,
):

    # Get a list of active strategies in production
    strategies = aggregator.assetsStrategiesAddresses()

    # Create Gelato job
    tx = yHarvest.createKeeperJob()

    resolverHash = tx.events[0][0]["resolverHash"]

    # Assign the Yearn Harvest as the keeper, check the resolver,
    # and execute when strat is harvestable
    for i in range(0, len(strategies)):
        strat_i = Contract(strategies[i])
        strat_i.setKeeper(yHarvest, {"from": gov})
        # print(f"Strategy {strategies[i]} has {strat_i.estimatedTotalAssets()/10**18:_} in assets.\n")
        assert strat_i.keeper() == yHarvest

    # Check if there are harvest jobs to run
    [canExec, execData] = yHarvest.checkHarvestStatus.call({"from": gelato.gelato()})

    while canExec:
        stratAddress = convert.to_address("0x" + execData.hex()[-40:])
        strat_i = Contract(stratAddress)
        isHarvestable = strat_i.harvestTrigger(baseFee)
        assert isHarvestable, "Contract and pytest params do not match"
        tx_i = gelato.exec(
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

        assert "HarvestedByGelato" in tx_i.events

        if "HarvestedByGelato" in tx_i.events:
            print(f"\033[92mSuccess! {stratAddress} was harvested.\033[0m\n")

        # Check if there are more harvest jobs to run
        [canExec, execData] = yHarvest.checkHarvestStatus.call(
            {"from": gelato.gelato()}
        )
