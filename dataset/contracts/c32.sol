pragma solidity ^0.4.22;

contract Closable {

  function close() {
    selfdestruct(msg.sender);
  }

}
