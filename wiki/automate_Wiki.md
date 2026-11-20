# SigmaOS-automate Component Wiki

## Overview
SigmaOS-automate provides a task automation engine with hooks, rules, and schedules for the SigmaOS operating system. It demonstrates the automation framework and rule-based scheduling within the SigmaOS ecosystem, following the principles of clear abstraction and deterministic task initialization.

## Principles
- Single Responsibility
- Task Automation Engine
- Fail-Fast on Automation Errors
- Deterministic Task Scheduling
- Clear Abstraction Over Automation APIs
- Composition over Inheritance for task rule extensions

## Architecture
SigmaOS-automate follows a task automation engine pattern:
- **Engine Core**: Provides task scheduling, hook execution, and rule evaluation primitives
- **Rule Management**: Supports rule definitions, conditions, and action triggers
- **Schedule Management**: Manages recurring tasks and time-based triggers
- **Hook Integration**: Integrates with system hooks and lifecycle events

## API
The component provides the following public APIs:
- `engine::schedule(task, interval)` - Schedule a recurring task
- `engine::hook::register(name, callback)` - Register a lifecycle hook
- `engine::rule::eval(rule, context)` - Evaluate a rule against a context
- `engine::status()` - Get engine status and active tasks/rules
- Error types for automation errors or invalid rule configurations

## Test Structure (Arrange-Act-ASSERT)
All tests follow the AAA pattern:
1. **Arrange**: Set up test environment with specific task automation configuration
2. **Act**: Execute the code under test (task scheduling, rule evaluation)
3. **Assert**: Verify the expected automation results

Example:
```rust
#[test]
fn test_engine_schedule_aaa() {
    // Arrange
    let task = "daily_cleanup";
    let interval = "24h";
    
    // Act
    let result = engine::schedule(task, interval);
    
    // Assert
    assert!(result.is_ok());
    assert!(engine::status().is_task_active("daily_cleanup"));
}
```

## Development
- Follows Rust best practices with `#![forbid(unsafe_code)]`
- Task automation initialization is best-effort; gracefully degrades on unsupported configurations
- Comprehensive error types for all automation failure scenarios
- Unit tests provided for task scheduling, rule evaluation, and hook integration
- Integration tests for full automation engine with system hooks and lifecycle events

## TODO
- Add support for additional task types and scheduling criteria
- Expand rule management capabilities (complex conditions, priority)
- Add schedule management (cron expressions, recurring patterns)
- Create integration tests with actual system hooks and lifecycle events
- Implement task priority and dependency management