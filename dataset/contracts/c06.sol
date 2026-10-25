pragma solidity ^0.4.22;

contract Vault {

  function withdrawAll() {
    msg.sender.transfer(this.balance);
  }

  function () public payable {
  }

}
