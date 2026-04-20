PROCEDURE inner(n);
BEGIN
  n := 99;
  WRITELN(n);
END;
BEGIN
  n := 7;
  ignore := inner(n);
  WRITELN(n);
END;
.
