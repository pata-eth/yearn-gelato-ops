import pytest
from brownie import YearnHarvest, accounts, Contract, Wei, interface

# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


@pytest.fixture(scope="module")
def aggregator():
    yield interface.IStrategyDataAggregator(
        "0x97D0bE2a72fc4Db90eD9Dbc2Ea7F03B4968f6938"
    )


# This is controlled by Gelato.
@pytest.fixture(scope="module")
def revertOnFailure():
    yield True


# `baseFee` is provided to harvestTrigger() in the checker function
# as the actual fee is not available there
@pytest.fixture(scope="module")
def baseFee():
    yield Wei("0.0000000001 ether")


# `gelatoFee` is the fee provided by Gelato executors to the exec() method
# We use it to simulate actual fees
@pytest.fixture(scope="module")
def gelatoFee():
    yield Wei("0.01 ether")


@pytest.fixture(scope="function")
def yHarvest(
    owner,
    gov,
    strategist_ms,
    whale_ftm,
    ftm_amount,
):
    yHarvest = YearnHarvest.deploy({"from": owner})
    yHarvest.setGovernance(gov, {"from": owner})
    yHarvest.acceptGovernance({"from": gov})
    yHarvest.setManagement(strategist_ms, {"from": owner})

    # get some FTM donations to pay for jobs
    whale_ftm.transfer(yHarvest, ftm_amount)

    # gas price is set to zero in the fork
    assert yHarvest.balance() == ftm_amount

    yield yHarvest


@pytest.fixture(scope="function")
def yHarvestDeployed():
    yield Contract("0xA8D8C5AcB1D8CCe9b21EF79713B776DF2EFA77bB")


@pytest.fixture(scope="function")
def gelato():
    yield interface.IGelatoOps("0x6EDe1597c05A0ca77031cBA43Ab887ccf24cd7e8")


# Fantom Curve Tricrypto
@pytest.fixture(scope="function")
def strategy(yHarvest, owner):
    strategy = Contract("0xA9a904B5567b5AFfb6bB334bea2f90F700EB221a")
    # Make the yHarvest contract the strategy's keeper
    strategy.setKeeper(yHarvest.address, {"from": owner})
    yield strategy


@pytest.fixture(scope="module")
def ftm_amount():
    yield Wei("50 ether")


@pytest.fixture(scope="module")
def crv():
    yield interface.ERC20("0x1E4F97b9f9F913c46F1632781732927B9019C68b")


@pytest.fixture(scope="module")
def native():
    yield "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


# Define any accounts in this section
@pytest.fixture(scope="module")
def gov(accounts):
    yield accounts.at("0xC0E2830724C946a6748dDFE09753613cd38f6767", force=True)


@pytest.fixture(scope="module")
def strategist_ms(accounts):
    # like governance, but better
    yield accounts.at("0x72a34AbafAB09b15E7191822A679f28E067C4a16", force=True)


@pytest.fixture(scope="module")
def owner(accounts):
    yield accounts.at("0x2757AE02F65dB7Ce8CF2b2261c58f07a0170e58e", force=True)


@pytest.fixture(scope="module")
def whale_ftm(accounts):
    yield accounts.at("0x431e81E5dfB5A24541b5Ff8762bDEF3f32F96354", force=True)
