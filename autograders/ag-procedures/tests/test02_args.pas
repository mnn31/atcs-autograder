PROCEDURE countUp(count, max);
IF count <= max THEN
BEGIN
   WRITELN(count);
   ignore := countUp(count + 1, max);
END;
BEGIN
   ignore := countUp(1, 4);
END;
.
