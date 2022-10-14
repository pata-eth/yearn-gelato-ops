from brownie import YearnHarvest, accounts, network, Contract, Wei, interface
import click


def main():
    print(f"You are using the '{network.show_active()}' network")
    owner = accounts.load(click.prompt("Account", type=click.Choice(accounts.load())))
    print(f"You are using: 'owner' [{owner.address}]")

    lens = interface.IYearnLens(
        "0x66a1A27f4b22DcAa24e427DCFFbf0cdDd9D35e0f"
    )

    gelato = interface.IGelatoOps("0xB3f5503f93d5Ef84b06993a1975B9D21B962892F")

    publish_source = click.confirm("Verify source on etherscan?")

    yHarvest = YearnHarvest.deploy(lens, gelato, {"from": owner}, publish_source=publish_source)

    # Tricrypto
    # strategy = Contract("0xcDD989d84f9B63D2f0B1906A2d9B22355316dE31")
    # strategy.setCreditThreshold(Wei("100 ether"), {"from": owner})
    # strategy.setKeeper(yHarvest.address, {"from": owner})

    # Run every 48 hours at a minimum
    # strategy.setMaxReportDelay(60 * 60 * 48, {"from": owner})

    # # TwoPool
    # strategy = Contract("0xF992FCEF771dF908f9B09Bb2619092f70AB21957")
    # strategy.setCreditThreshold(Wei("100 ether"), {"from": owner}) # ~100 USD threshold
    # strategy.setKeeper(yHarvest.address, {"from": owner})
    # strategy.setMaxReportDelay(60 * 60 * 48, {"from": owner})

    # # Curve Spell MIM
    # strategy = Contract("0xF992FCEF771dF908f9B09Bb2619092f70AB21957")
    # strategy.setKeeper(yHarvest.address, {"from": owner})
    # strategy.setMaxReportDelay(60 * 60 * 48, {"from": owner})

    # Fund the yHarvest contract
    owner.transfer(yHarvest, "0.2 ether")

    assert yHarvest.balance() == Wei("0.2 ether")

    # Create Gelato job
    tx = yHarvest.initiateStrategyMonitor()

    tx.info()
