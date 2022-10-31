from brownie import YearnGelatoOps, accounts, network, Wei, interface
import click


def main():
    print(f"You are using the '{network.show_active()}' network")
    owner = accounts.load(
        click.prompt("Account", type=click.Choice(accounts.load()))
    )
    print(f"You are using: 'owner' [{owner.address}]")

    lens = interface.IYearnLens("0xD3A93C794ee2798D8f7906493Cd3c2A835aa0074")

    gelato = interface.IGelatoOps("0x340759c8346A1E6Ed92035FB8B6ec57cE1D82c2c")

    yGO = YearnGelatoOps.deploy(lens, gelato, {"from": owner})

    # Fund the yGO contract
    amount = Wei("0.2 ether")
    owner.transfer(yGO, amount)

    assert yGO.balance() == amount

    # Create Gelato job
    tx = yGO.initiateStrategyMonitor()

    tx.info()
