"""One module per feature, each with apply(cfg). A module may set PROVIDES
and REQUIRES (capabilities such as "packages"; the runner orders providers
first) and GATE (default: features.<its name>). Importing a module must have
no side effects, since every module is imported to order them."""
