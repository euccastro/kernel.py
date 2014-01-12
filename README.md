kernel.py
=========

Naive implementation of [Kernel](http://web.cs.wpi.edu/~jshutt/kernel.html) in Python.

The longer-term goal is to serve as a starting point for a JIT-enabled RPython implementation.  But that will be spun off as a different project.  This one will remain focused on simplicity and understandability.  Efficiency is not a concern.

This implementation doesn't aim to be *comprehensive*, as in the [R-1RS](ftp://ftp.cs.wpi.edu/pub/techreports/pdf/05-07.pdf).  In particular, mutable pairs/lists are not in the plans.

Known incompatibilities:

- Identifiers are case sensitive.

Other temporary incompatibilities will exist, but all not listed above are meant to be fixed.

Extensions:

- λ is allowed in an identifier.
