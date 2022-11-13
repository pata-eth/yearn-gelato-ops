# The Gelato proxy contract now has two implementations in Optimism as follows:
#
# Proxy => 0x340759c8346A1E6Ed92035FB8B6ec57cE1D82c2c
#    New Implementation => 0x5a70E998bE2Bb781Af0E33CaB598Ec2C0b2bBbb5
#    Old Implementation => 0xa5f9b728ecEB9A1F6FCC89dcc2eFd810bA4Dec41
#
# Issue: tests are failing because Brownie incorrectly uses the new
# implementation as fallback when it should use the old implementation
#
# To reproduce, launch optimism fork
from brownie import Contract

# Instantiate gelato proxy
gelato = Contract("0x340759c8346A1E6Ed92035FB8B6ec57cE1D82c2c")

# random address to make the call below work. Inputs don't need to make sense
# to repro.
owner = "0x2757AE02F65dB7Ce8CF2b2261c58f07a0170e58e"

tx = gelato.exec(
    10**15, owner, owner, False, True, "0x", owner, "0x", {"from": owner}
)

tx.call_trace(True)

# Call trace for '0xfcc2ef5ca81cbbd131df81f7e316fc223ec246846ee9b04ed46d4583c3e12f27':
# Initial call cost  [23172 gas]
# EIP173Proxy.exec  0:424  [144 / 3012 gas]
# └── Proxy._fallback  34:424  [954 / 2868 gas]
#     │
#     └── Ops  [DELEGATECALL]  49:408  [1914 gas]
#             ├── address: 0x5a70E998bE2Bb781Af0E33CaB598Ec2C0b2bBbb5 <= WRONG IMPLEMENTATION!
#             └── calldata: 0x0ea65a6300000000000000000000000000000000000000000000000000038d7ea4c680000000000000000000000000002757ae02f65db7ce8cf2b2261c58f07a0170e58e0000000000000000000000002757ae02f65db7ce8cf2b2261c58f07a0170e58e0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000002757ae02f65db7ce8cf2b2261c58f07a0170e58e000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000

# The signature + calldata are correct but the tx fails because that signature
# does not exist in the fallback contract brownie is trying to use

# new implementation function
# 0x5a70E998bE2Bb781Af0E33CaB598Ec2C0b2bBbb5
# function exec(
#         address _taskCreator,
#         address _execAddress,
#         bytes memory _execData,
#         LibDataTypes.ModuleData calldata _moduleData,
#         uint256 _txFee,
#         address _feeToken,
#         bool _useTaskTreasuryFunds,
#         bool _revertOnFailure
#     ) external {...}

# old implementation function
# 0xa5f9b728ecEB9A1F6FCC89dcc2eFd810bA4Dec41
# function exec(
#         uint256 _txFee,
#         address _feeToken,
#         address _taskCreator,
#         bool _useTaskTreasuryFunds,
#         bool _revertOnFailure,
#         bytes32 _resolverHash,
#         address _execAddress,
#         bytes calldata _execData
#     ) external {...}
