#ifndef TEST_ACTION_GPIO_H
#define TEST_ACTION_GPIO_H

/* ============================================================
 *  test_action_gpio.h — Interface publique du test GPIO
 *
 *  Appeler test_action_gpio_main() depuis main.c
 *  après test_rules_debug_main() et avant osKernelStart().
 *
 *  Dans main.c :
 *    osKernelInitialize();
 *    test_debug_main();        // reader
 *    test_rules_debug_main();  // rules engine
 *    test_action_gpio_main();  // GPIO consumer ← ici
 *    osKernelStart();
 * ============================================================ */

void test_action_gpio_main(void);

#endif /* TEST_ACTION_GPIO_H */
