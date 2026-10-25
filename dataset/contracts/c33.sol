pragma solidity ^0.4.19;

contract Counter {
    uint public count = 1;

    function run(uint256 input) public {
        count -= input;
    }
}
