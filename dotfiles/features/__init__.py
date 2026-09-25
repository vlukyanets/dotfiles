"""One feature per module: a Feature subclass whose nested classes, named
after platform classes (Arch, Linux, …), are its strategies. The module's
name is the feature's, so features.<name>.enabled switches it; the order
comes from the package graph and what each strategy requires(). Importing a module must have no side effects."""
