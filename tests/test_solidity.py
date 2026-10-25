from auditor.solidity import (
    enclosing_function,
    find_anchor,
    has_comments,
    normalize,
    sanitize,
    strip_comments,
)


def test_strip_comments_keeps_strings():
    src = 'string a = "http://x // not a comment"; // real\nuint b; /* gone */ uint c;\n'
    out = strip_comments(src)
    assert '"http://x // not a comment"' in out
    assert "real" not in out and "gone" not in out
    assert "uint c;" in out


def test_block_comment_keeps_line_count():
    src = "a;\n/* one\ntwo\nthree */\nb;\n"
    assert strip_comments(src).count("\n") == src.count("\n")


def test_has_comments():
    assert has_comments("uint a; // x")
    assert not has_comments('string s = "//";')


def test_normalize_collapses_blank_runs():
    assert normalize("a  \n\n\n\nb\n\n") == "a\n\nb\n"


def test_sanitize_renames_whole_words_only():
    out = sanitize("contract Foo { function FooBar() {} } // Foo", {"Foo": "Baz"})
    assert "contract Baz" in out and "FooBar" in out and "//" not in out


def test_find_anchor_ignores_whitespace():
    src = "a;\nrequire( x  ==  y );\nb;\n"
    assert find_anchor(src, "require(x == y);") == [2]


CONTRACT = """pragma solidity ^0.4.24;
contract C {
    uint x;
    modifier only {
        require(msg.sender == address(0));
        _;
    }
    constructor() public {
        x = 1;
    }
    function transfer(
        uint a,
        uint b)
      public
    {
        x = a + b;
    }
    function () public payable {}
    function g() public { x = 2; }
}
"""


def test_enclosing_function():
    assert enclosing_function(CONTRACT, 3) == "<contract-level>"
    assert enclosing_function(CONTRACT, 5) == "only"
    assert enclosing_function(CONTRACT, 9) == "constructor"
    assert enclosing_function(CONTRACT, 12) == "transfer"
    assert enclosing_function(CONTRACT, 16) == "transfer"
    assert enclosing_function(CONTRACT, 18) == "fallback"
    assert enclosing_function(CONTRACT, 19) == "g"


def test_sanitize_drops_comment_only_lines():
    src = "function f() {\n    // explain\n    x = 1;\n\n    y = 2; // trailing\n}\n"
    assert sanitize(src) == "function f() {\n    x = 1;\n\n    y = 2;\n}\n"
