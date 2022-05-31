from brownie import convert, chain, accounts


def test_deploted(yHarvestDeployed, gelato):

    resolverHash = "0xd582acf382800a91258384972e53568daee0f6731e936d53f38ac9503ca8c7a2"

    [canExec, execData] = yHarvestDeployed.checkHarvestStatus.call(
        {"from": gelato.gelato()}
    )
    gelatoFee = 10**8

    feeToken = yHarvestDeployed.feeToken()

    tx = gelato.exec(
        gelatoFee,
        feeToken,
        yHarvestDeployed.address,
        False,  # do not use Gelato Treasury for payment
        True,
        resolverHash,
        yHarvestDeployed.address,
        execData,
        {"from": gelato.gelato()},
    )

    chain.undo()

    stratAddress = convert.to_address("0x" + execData.hex()[-40:])

    tx = yHarvestDeployed.harvestStrategy(stratAddress, {"from": gelato.gelato()})
    tx.call_trace(True)
