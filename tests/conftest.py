import pytest
from brownie import YearnHarvest, Contract, Wei, interface

# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


@pytest.fixture(scope="module")
def lens():
    yield interface.IYearnLens(
        "0x66a1A27f4b22DcAa24e427DCFFbf0cdDd9D35e0f"
    )


# `baseFee` is provided to harvestTrigger() in the checker function
# as the actual fee is not available there
@pytest.fixture(scope="module")
def baseFee():
    yield Wei("0.0000000001 ether")


# `gelatoFee` is the fee provided by Gelato executors to the exec() method
# We use it to simulate actual fees
@pytest.fixture(scope="module")
def gelatoFee():
    yield Wei("0.001 ether")


@pytest.fixture(scope="function")
def yHarvest(
    lens,
    gelato,
    owner,
    whale,
    amount,
):

    yHarvest = YearnHarvest.deploy(lens.address, gelato.address, {"from": owner})

    # get some AETH donations to pay for jobs
    whale.transfer(yHarvest, amount)

    # gas price is set to zero in the fork
    assert yHarvest.balance() == amount

    yield yHarvest


# @pytest.fixture(scope="function")
# def yHarvestDeployed():
#     yield Contract("0x9AB353057CF41CfbA981a37e6C8F3942cc0147b6")


@pytest.fixture(scope="function")
def gelato():
    yield interface.IGelatoOps("0xB3f5503f93d5Ef84b06993a1975B9D21B962892F")


# Arbitrum Curve Tricrypto
@pytest.fixture(scope="function")
def strategy(yHarvest, owner):
    strategy = Contract("0xcDD989d84f9B63D2f0B1906A2d9B22355316dE31")
    # Make the yHarvest contract the strategy's keeper
    strategy.setKeeper(yHarvest.address, {"from": owner})
    strategy.setForceHarvestTriggerOnce(True, {"from": owner})
    yield strategy


@pytest.fixture(scope="function")
def strategy_not_onboarded(yHarvest, owner):
    strategy = Contract("0xf1C3047C6310806de1d25535BC50748815066a7b")
    yield strategy


@pytest.fixture(scope="module")
def amount():
    yield Wei("50 ether")


@pytest.fixture(scope="module")
def crv():
    yield interface.ERC20("0x11cDb42B0EB46D95f990BeDD4695A6e3fA034978")


@pytest.fixture(scope="module")
def native():
    yield "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


# Define any accounts in this section
@pytest.fixture(scope="module")
def gov(accounts):
    yield accounts.at("0xb6bc033D34733329971B938fEf32faD7e98E56aD", force=True)


@pytest.fixture(scope="module")
def owner(accounts):
    yield accounts.at("0x2757AE02F65dB7Ce8CF2b2261c58f07a0170e58e", force=True)


@pytest.fixture(scope="module")
def whale(accounts):
    yield accounts.at("0xd664DCcF95062eE26c6BFAa1f6bC1b5e68CC2243", force=True)
