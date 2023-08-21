// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.8.15;

interface ICommonReportTrigger {
    function strategyReportTrigger(address _strategy) external view returns (bool, bytes memory);
    function strategyTendTrigger(address _strategy) external view returns (bool, bytes memory);
}
