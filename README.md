    # SigmaOS-automate

    Task automation engine (hooks, rules, schedules)

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/linuxmint/automate

    ## Design principles applied
    - **Declarative over Imperative**
- **Plan Before Apply**
- **Fail-Fast**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `add-rule, list, run, schedule-plan`

    ```
    $ sigma-automate add-rule --store rules.json --trigger battery-low \
      --when percent lt 20 --then notify "Battery low"
$ sigma-automate list --store rules.json
$ sigma-automate run --store rules.json --event battery-low --payload percent=15
$ sigma-automate schedule-plan --store rules.json --rule nightly-clean --daily 02:30

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
