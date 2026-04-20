PROCEDURE add1(n);
add1 := n + 1;
PROCEDURE times2(n);
times2 := n * 2;
BEGIN
  WRITELN(add1(times2(5)));
END;
.
