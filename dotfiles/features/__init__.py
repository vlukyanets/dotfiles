"""One module per feature, each with apply(cfg). A module may set NEEDS
(the steps it runs after) and GATE (default: features.<its name>); importing
it must have no side effects, since every module is imported to order them."""
