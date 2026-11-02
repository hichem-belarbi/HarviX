#ifndef TEST_RULES_DEBUG_H
#define TEST_RULES_DEBUG_H

/* Appeler depuis main() APRÈS test_debug_main() et osKernelInitialize(),
 * mais AVANT osKernelStart() */
void test_rules_debug_main(void);

#endif /* TEST_RULES_DEBUG_H */
