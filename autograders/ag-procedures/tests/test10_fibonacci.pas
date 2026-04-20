PROCEDURE fib(n);
BEGIN
  fib := 1;
  IF n > 1 THEN fib := fib(n - 1) + fib(n - 2);
END;
BEGIN
  WRITELN(fib(0));
  WRITELN(fib(1));
  WRITELN(fib(5));
  WRITELN(fib(8));
END;
.
