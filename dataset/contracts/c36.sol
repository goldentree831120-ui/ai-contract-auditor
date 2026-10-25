pragma solidity ^0.5.0;

contract TimedCrowdsale {

  event Finished();
  event notFinished();

  function isSaleFinished() private returns (bool) {
    return block.timestamp >= 1546300800;
  }

  function run() public {
  	if (isSaleFinished()) {
  		emit Finished();
  	} else {
  		emit notFinished();
  	}
  }

}
