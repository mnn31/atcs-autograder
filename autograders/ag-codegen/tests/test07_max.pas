VAR a, b, m;
BEGIN
  a := 10;
  b := 20;
  m := a;
  IF b > m THEN m := b;
  WRITELN(m);
END;
.
