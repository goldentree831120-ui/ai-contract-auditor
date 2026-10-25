pragma solidity 0.4.25;

contract Caller {

  function callA(address callee) public {
  	require(callee.call());
  }

  function callB(address callee) public {
    callee.call();
  }
}
