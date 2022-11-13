from brownie import reverts


def test_sweep(yGO, owner, gov, amount, usdc, usdc_amount, native):

    assert yGO.balance() == amount
    assert usdc.balanceOf(yGO) == usdc_amount

    with reverts("!governance"):
        yGO.sweep(usdc, {"from": gov})

    yGO.setGovernance(gov, {"from": owner})
    yGO.acceptGovernance({"from": gov})

    old_usdc_bal = usdc.balanceOf(gov)
    yGO.sweep(usdc, {"from": gov})

    new_usdc_balance = usdc.balanceOf(gov)

    assert (new_usdc_balance - old_usdc_bal) == usdc_amount
    assert usdc.balanceOf(yGO) == 0

    old_native_bal = gov.balance()
    yGO.sweep(native, {"from": gov})
    new_native_bal = gov.balance()

    assert (new_native_bal - old_native_bal) == amount
    assert yGO.balance() == 0
