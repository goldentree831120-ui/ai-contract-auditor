// Example contract for trying the CLI. Written for this project (MIT), not from the dataset.
// It contains deliberate weaknesses; do not deploy it.
pragma solidity ^0.4.24;

contract TipJar {
    address public owner;
    mapping(address => uint) public tips;

    constructor() public {
        owner = msg.sender;
    }

    function tip() public payable {
        tips[msg.sender] += msg.value;
    }

    function refund() public {
        uint amount = tips[msg.sender];
        require(msg.sender.call.value(amount)());
        tips[msg.sender] = 0;
    }

    function sweep(address to) public {
        require(tx.origin == owner);
        to.transfer(address(this).balance);
    }
}
