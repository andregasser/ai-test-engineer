# Testing Standards & Guidelines

This document serves as the **SINGLE SOURCE OF TRUTH** for all automated and manual testing in this project.
All AI agents and developers must adhere strictly to these rules.

## 1. Project Context
- Environment: Spring Boot 3.5.9, Java 21, Gradle multi-module.

## 2. Testing Frameworks & Libraries

- **Test Runner:** JUnit 5 (Jupiter) ONLY.
  - **Do NOT use:** JUnit 4 (`org.junit.Test`, `org.junit.runner.RunWith`).
  - **Use:** `org.junit.jupiter.api.Test`, `@ExtendWith(MockitoExtension.class)`.
- **Mocking:** Mockito.
  - Use `Mockito.mock()`, `Mockito.when()`, `Mockito.verify()`.
  - Prefer `@Mock` and `@InjectMocks` annotations with the Mockito extension.
  - It is allowed to use Mockito and WireMock in a single test. They can co-exist.
- **HTTP Mocking:** WireMock.
  - Used for integration tests to mock external API responses.
- **Assertions:** AssertJ.
  - **Preferred:** `assertThat(actual).isEqualTo(expected)`.
  - **Avoid:** `assertEquals(expected, actual)` (JUnit native assertions).

## 3. Test Types

- **Unit Tests:**
  - Must mock ALL external dependencies (repositories, clients, other services).
  - Must execute quickly (ms).
  - Must NOT load the Spring Context (`@SpringBootTest` is forbidden for unit tests).
  - Place in `src/test/java` in the same package as the class under test.
- **Integration Tests:**
  - Use `@SpringBootTest` only when testing actual Spring wiring or full contexts.
  - Use `Testcontainers` for DB/Messaging dependencies if needed.
  - For integration tests where it is important to assert the outgoing request in detail (HTTP headers, payloads, etc...) WireMock must be used.

## 4. Coverage Reports

In this project, JaCoCo coverage reports are located in the following directories:

- **Multi-module Aggregate Report:** build/reports/jacoco/root/jacocoRootReport.xml (usually found at the project root 
  after running an aggregate task).
- **Individual Module Reports:** [module-name]/build/reports/jacoco/test/jacocoTestReport.xml.

## 5. Naming Conventions

- **Unit Test Class Name:** `<ProductionClassName>Test` (e.g. `UserServiceTest.java`)
- **Integration Test Class Name:** `<ProductionClassName>IT` (e.g. `UserServiceIT.java`)
- **Method Name:** Snake case is preferred for readability.
  - Pattern: `should_<ExpectedBehavior>_when_<StateOrInput>`
  - Example: `should_return_active_user_when_user_exists()`

## 6. Coding Style

- **Pattern:** AAA (Arrange, Act, Assert).
  ```java
  @Test
  void should_calculate_total_correctly() {
      // Arrange
      var calculator = new Calculator();
      
      // Act
      var result = calculator.add(2, 3);
      
      // Assert
      assertThat(result).isEqualTo(5);
  }
  ```
- **Logging:** Do NOT use `System.out.println`. Use SLF4J if debug output is strictly necessary (rare).
- **Complexity:** Keep tests simple. No complex logic or loops inside tests.

## 7. Forbidden Practices

- ❌ No `Thread.sleep()`. Use Awaitility if async waiting is needed.
- ❌ No `@Autowired` in simple unit tests. Use constructor injection or `@InjectMocks`.
- ❌ No `catch (Exception e) { fail() }`. Let the test throw the exception; JUnit will handle it.
