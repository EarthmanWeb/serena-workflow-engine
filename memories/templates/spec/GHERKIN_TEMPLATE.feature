@{{feature_key}}
Feature: {{feature_name}}
  {{feature_description}}

  Background:
    Given the system is initialized

  # Happy Path
  Scenario: [Primary success scenario]
    Given [precondition]
    When [user action]
    Then [expected outcome]

  # Error Handling
  Scenario: [Error scenario]
    Given [precondition]
    When [invalid action]
    Then [error response]

  # Edge Cases
  Scenario: [Edge case scenario]
    Given [boundary condition]
    When [action at boundary]
    Then [expected behavior at boundary]
