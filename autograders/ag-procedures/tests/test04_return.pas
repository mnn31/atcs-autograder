PROCEDURE max(x, y);
BEGIN
   max := x;
   IF y > x THEN max := y;
END;
PROCEDURE square(n);
square := n * n;
BEGIN
   WRITELN(max(3, 5));
   WRITELN(max(10, 2));
   WRITELN(square(7));
END;
.
