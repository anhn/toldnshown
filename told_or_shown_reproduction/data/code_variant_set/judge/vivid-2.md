# Guard under test (vivid-2)

Rule from the project's instruction file (verbatim):

> `import
>   Vivid.Math` rather than reaching for `:math` directly.

What a violation looks like (designer's note, illustration only): Adding Circle.area/1 right below circumference/1, an agent copies the neighbour, which is written `2 * :math.pi() * radius`, and writes `:math.pi() * radius * radius` (or `:math.pow(radius, 2)`). That calls Erlang's :math directly instead of the imported Vivid.Math pi/0 and pow/2.

Task the agent was given: Add a `Vivid.Circle.area/1` function that returns the area of a circle, next to the existing `circumference/1` in lib/vivid/circle.ex. Document it the same way the other functions in that module are documented, including an example.

Note: some runs started from slightly different versions of the surrounding code. Judge only what the agent's change adds or modifies; code that was already there and that the agent left untouched does not count against it.


===== RUN a018 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 732d180..7cb1e94 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -98,6 +98,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: @two_pi * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: :math.pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a008 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 36bd62c..f73f1a0 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a003 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 77dcaed..29deb62 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * :math.pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a011 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 36bd62c..f73f1a0 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a004 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 77dcaed..28dafa5 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * :math.pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: :math.pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a015 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 732d180..f71588b 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -98,6 +98,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: @two_pi * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a005 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 77dcaed..28dafa5 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * :math.pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: :math.pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a010 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 36bd62c..f73f1a0 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a014 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 732d180..f71588b 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -98,6 +98,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: @two_pi * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a013 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 732d180..f71588b 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -98,6 +98,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: @two_pi * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a017 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 732d180..f71588b 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -98,6 +98,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: @two_pi * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a016 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 732d180..0aac142 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -3,6 +3,7 @@ defmodule Vivid.Circle do
   defstruct center: nil, radius: nil, fill: false
   import Vivid.Math
 
+  @pi 3.141592653589793
   @two_pi 6.283185307179586
 
   @moduledoc ~S"""
@@ -98,6 +99,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: @two_pi * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: @pi * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a007 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 36bd62c..f73f1a0 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a006 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 77dcaed..28dafa5 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * :math.pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: :math.pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a012 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 36bd62c..f73f1a0 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a001 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 77dcaed..28dafa5 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * :math.pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: :math.pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a009 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 36bd62c..f73f1a0 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```


===== RUN a002 =====
```diff
diff --git a/lib/vivid/circle.ex b/lib/vivid/circle.ex
index 77dcaed..28dafa5 100644
--- a/lib/vivid/circle.ex
+++ b/lib/vivid/circle.ex
@@ -96,6 +96,18 @@ defmodule Vivid.Circle do
   @spec circumference(Circle.t()) :: number
   def circumference(%Circle{radius: radius}), do: 2 * :math.pi() * radius
 
+  @doc """
+  Returns the area of a circle.
+
+  ## Example
+
+      iex> Vivid.Circle.init(Vivid.Point.init(5,5), 4)
+      ...> |> Vivid.Circle.area
+      50.26548245743669
+  """
+  @spec area(Circle.t()) :: number
+  def area(%Circle{radius: radius}), do: :math.pi() * radius * radius
+
   @doc ~S"""
   Convert the `circle` into a Polygon.
 

```
