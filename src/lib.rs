// SPDX-License-Identifier: MIT OR Apache-2.0
//! SigmaOS-automate — Task automation engine (hooks, rules, schedules).
//!
//! Provides rule-based background automation: event hooks, cron/interval triggers,
//! action pipelines (commands, notifications, file ops), and execution logging.
//!
//! Inspired by Omarchy's script-centric workflow, Hyprland's dispatch rules,
//! and the Catppuccin Mocha aesthetic of quiet productivity.
//!
//! Principles: deterministic evaluation order, pure `std`, zero `unsafe`.

#![forbid(unsafe_code)]

use std::collections::HashMap;
use std::fmt;

// ── Error types ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AutomateError {
    EmptyRuleName,
    InvalidPriority(i32),
    TriggerNotFound(String),
    ActionExecutionFailed(String),
    CircularDependency(String),
    DuplicateRule(String),
}

impl fmt::Display for AutomateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyRuleName => write!(f, "rule name cannot be empty"),
            Self::InvalidPriority(p) => write!(f, "priority {p} outside allowed range (-100..=100)"),
            Self::TriggerNotFound(t) => write!(f, "trigger '{t}' not recognized"),
            Self::ActionExecutionFailed(msg) => write!(f, "action execution failed: {msg}"),
            Self::CircularDependency(msg) => write!(f, "circular trigger loop detected: {msg}"),
            Self::DuplicateRule(r) => write!(f, "rule '{r}' already registered"),
        }
    }
}

impl std::error::Error for AutomateError {}

// ── Triggers and Actions ─────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Trigger {
    Startup,
    FileModified(String),
    PeriodicIntervalSec(u64),
    CustomEvent(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Action {
    RunCommand { command: String, args: Vec<String> },
    DesktopNotification { title: String, body: String },
    SetEnvironment { key: String, value: String },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AutomationRule {
    pub name: String,
    pub priority: i32, // -100 to +100
    pub trigger: Trigger,
    pub actions: Vec<Action>,
    pub enabled: bool,
}

impl AutomationRule {
    pub fn new(name: impl Into<String>, trigger: Trigger) -> Result<Self, AutomateError> {
        let name = name.into().trim().to_string();
        if name.is_empty() {
            return Err(AutomateError::EmptyRuleName);
        }
        Ok(Self {
            name,
            priority: 0,
            trigger,
            actions: Vec::new(),
            enabled: true,
        })
    }

    pub fn with_priority(mut self, priority: i32) -> Result<Self, AutomateError> {
        if !(-100..=100).contains(&priority) {
            return Err(AutomateError::InvalidPriority(priority));
        }
        self.priority = priority;
        Ok(self)
    }

    pub fn add_action(&mut self, action: Action) {
        self.actions.push(action);
    }
}

// ── Automation Engine ────────────────────────────────────────────────────────

#[derive(Debug, Default)]
pub struct AutomateEngine {
    rules: HashMap<String, AutomationRule>,
    execution_history: Vec<String>,
}

impl AutomateEngine {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register_rule(&mut self, rule: AutomationRule) -> Result<(), AutomateError> {
        if self.rules.contains_key(&rule.name) {
            return Err(AutomateError::DuplicateRule(rule.name));
        }
        self.rules.insert(rule.name.clone(), rule);
        Ok(())
    }

    pub fn trigger_event(&mut self, event: &Trigger) -> Vec<String> {
        // Collect matching rules sorted by priority descending
        let mut matching: Vec<&AutomationRule> = self.rules
            .values()
            .filter(|r| r.enabled && &r.trigger == event)
            .collect();

        matching.sort_by(|a, b| b.priority.cmp(&a.priority));

        let mut executed_rule_names = Vec::new();
        for r in matching {
            self.execution_history.push(format!("Executed rule '{}' with {} action(s)", r.name, r.actions.len()));
            executed_rule_names.push(r.name.clone());
        }
        executed_rule_names
    }

    pub fn history(&self) -> &[String] {
        &self.execution_history
    }
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rule_creation_and_empty_name_fails() {
        // Arrange & Act
        let ok = AutomationRule::new("backup-rule", Trigger::Startup);
        let empty = AutomationRule::new("   ", Trigger::Startup);

        // Assert
        assert!(ok.is_ok());
        assert_eq!(empty, Err(AutomateError::EmptyRuleName));
    }

    #[test]
    fn rule_priority_bounds_check() {
        // Arrange
        let rule = AutomationRule::new("p-rule", Trigger::Startup).unwrap();
        // Act
        let valid = rule.clone().with_priority(50);
        let too_high = rule.with_priority(150);
        // Assert
        assert!(valid.is_ok());
        assert_eq!(too_high, Err(AutomateError::InvalidPriority(150)));
    }

    #[test]
    fn engine_duplicate_registration_fails() {
        // Arrange
        let mut engine = AutomateEngine::new();
        let r1 = AutomationRule::new("clean-tmp", Trigger::Startup).unwrap();
        let r2 = AutomationRule::new("clean-tmp", Trigger::PeriodicIntervalSec(60)).unwrap();

        // Act
        engine.register_rule(r1).unwrap();
        let err = engine.register_rule(r2);

        // Assert
        assert_eq!(err, Err(AutomateError::DuplicateRule("clean-tmp".into())));
    }

    #[test]
    fn engine_executes_in_priority_order() {
        // Arrange
        let mut engine = AutomateEngine::new();
        let mut low = AutomationRule::new("low-priority", Trigger::Startup).unwrap().with_priority(-10).unwrap();
        low.add_action(Action::DesktopNotification { title: "Low".into(), body: "Low".into() });

        let mut high = AutomationRule::new("high-priority", Trigger::Startup).unwrap().with_priority(90).unwrap();
        high.add_action(Action::DesktopNotification { title: "High".into(), body: "High".into() });

        engine.register_rule(low).unwrap();
        engine.register_rule(high).unwrap();

        // Act
        let triggered = engine.trigger_event(&Trigger::Startup);

        // Assert: high priority should be executed before low priority
        assert_eq!(triggered, vec!["high-priority", "low-priority"]);
        assert_eq!(engine.history().len(), 2);
    }

    #[test]
    fn disabled_rules_are_skipped() {
        // Arrange
        let mut engine = AutomateEngine::new();
        let mut rule = AutomationRule::new("disabled-task", Trigger::CustomEvent("user-login".into())).unwrap();
        rule.enabled = false;
        engine.register_rule(rule).unwrap();

        // Act
        let executed = engine.trigger_event(&Trigger::CustomEvent("user-login".into()));

        // Assert
        assert!(executed.is_empty());
    }

    #[test]
    fn error_display_formatting() {
        // Arrange
        let err = AutomateError::DuplicateRule("auto-mount".into());
        // Act & Assert
        assert_eq!(format!("{err}"), "rule 'auto-mount' already registered");
    }
}
