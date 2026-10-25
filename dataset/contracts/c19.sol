pragma solidity ^0.4.19;

contract Multiplier {
    uint public count = 2;

    function run(uint256 input) public {
        count = mul(count, input);
    }

    function mul(uint256 a, uint256 b) internal pure returns (uint256) {
      if (a == 0) {
        return 0;
      }

      uint256 c = a * b;
      require(c / a == b);

      return c;
    }
}
