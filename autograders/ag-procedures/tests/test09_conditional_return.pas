PROCEDURE absval(n);
BEGIN
  absval := n;
  IF n < 0 THEN absval := 0 - n;
END;
BEGIN
  WRITELN(absval(5));
  WRITELN(absval(0 - 8));
  WRITELN(absval(0));
END;
.
