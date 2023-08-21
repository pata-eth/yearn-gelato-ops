// SPDX-License-Identifier: GPL-3.0
pragma solidity 0.8.15;

interface StrategyAPI {
    function tend() external;
    function report() external returns (uint256 _profit, uint256 _loss);
    function keeper() external view returns (address);
}
