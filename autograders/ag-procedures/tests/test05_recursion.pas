PROCEDURE fact(n);
BEGIN
   fact := 1;
   IF n > 0 THEN fact := n * fact(n - 1);
END;
BEGIN
   WRITELN(fact(0));
   WRITELN(fact(1));
   WRITELN(fact(5));
   WRITELN(fact(6));
END;
.
