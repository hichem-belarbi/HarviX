################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (13.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Core/Src/action_queue.c \
../Core/Src/bh1750_driver.c \
../Core/Src/commander.c \
../Core/Src/freertos.c \
../Core/Src/history_buffer.c \
../Core/Src/i2c_helper.c \
../Core/Src/main.c \
../Core/Src/ntc_driver.c \
../Core/Src/pattern_parser.c \
../Core/Src/primitives.c \
../Core/Src/reader.c \
../Core/Src/rules_engine.c \
../Core/Src/rules_store.c \
../Core/Src/rx.c \
../Core/Src/sensor_dispatch.c \
../Core/Src/stm32f4xx_hal_msp.c \
../Core/Src/stm32f4xx_hal_timebase_tim.c \
../Core/Src/stm32f4xx_it.c \
../Core/Src/syscalls.c \
../Core/Src/sysmem.c \
../Core/Src/system_stm32f4xx.c \
../Core/Src/test_action_gpio.c \
../Core/Src/test_reader_debug.c \
../Core/Src/test_rules_debug.c \
../Core/Src/uart_tx_queue.c 

OBJS += \
./Core/Src/action_queue.o \
./Core/Src/bh1750_driver.o \
./Core/Src/commander.o \
./Core/Src/freertos.o \
./Core/Src/history_buffer.o \
./Core/Src/i2c_helper.o \
./Core/Src/main.o \
./Core/Src/ntc_driver.o \
./Core/Src/pattern_parser.o \
./Core/Src/primitives.o \
./Core/Src/reader.o \
./Core/Src/rules_engine.o \
./Core/Src/rules_store.o \
./Core/Src/rx.o \
./Core/Src/sensor_dispatch.o \
./Core/Src/stm32f4xx_hal_msp.o \
./Core/Src/stm32f4xx_hal_timebase_tim.o \
./Core/Src/stm32f4xx_it.o \
./Core/Src/syscalls.o \
./Core/Src/sysmem.o \
./Core/Src/system_stm32f4xx.o \
./Core/Src/test_action_gpio.o \
./Core/Src/test_reader_debug.o \
./Core/Src/test_rules_debug.o \
./Core/Src/uart_tx_queue.o 

C_DEPS += \
./Core/Src/action_queue.d \
./Core/Src/bh1750_driver.d \
./Core/Src/commander.d \
./Core/Src/freertos.d \
./Core/Src/history_buffer.d \
./Core/Src/i2c_helper.d \
./Core/Src/main.d \
./Core/Src/ntc_driver.d \
./Core/Src/pattern_parser.d \
./Core/Src/primitives.d \
./Core/Src/reader.d \
./Core/Src/rules_engine.d \
./Core/Src/rules_store.d \
./Core/Src/rx.d \
./Core/Src/sensor_dispatch.d \
./Core/Src/stm32f4xx_hal_msp.d \
./Core/Src/stm32f4xx_hal_timebase_tim.d \
./Core/Src/stm32f4xx_it.d \
./Core/Src/syscalls.d \
./Core/Src/sysmem.d \
./Core/Src/system_stm32f4xx.d \
./Core/Src/test_action_gpio.d \
./Core/Src/test_reader_debug.d \
./Core/Src/test_rules_debug.d \
./Core/Src/uart_tx_queue.d 


# Each subdirectory must supply rules for building sources it contributes
Core/Src/%.o Core/Src/%.su Core/Src/%.cyclo: ../Core/Src/%.c Core/Src/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m4 -std=gnu11 -g3 -DDEBUG -DUSE_HAL_DRIVER -DSTM32F429xx -c -I../Core/Inc -I../FATFS/Target -I../FATFS/App -I../Drivers/STM32F4xx_HAL_Driver/Inc -I../Drivers/STM32F4xx_HAL_Driver/Inc/Legacy -I../Middlewares/Third_Party/FreeRTOS/Source/include -I../Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2 -I../Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F -I../Middlewares/Third_Party/FatFs/src -I../Drivers/CMSIS/Device/ST/STM32F4xx/Include -I../Drivers/CMSIS/Include -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Core-2f-Src

clean-Core-2f-Src:
	-$(RM) ./Core/Src/action_queue.cyclo ./Core/Src/action_queue.d ./Core/Src/action_queue.o ./Core/Src/action_queue.su ./Core/Src/bh1750_driver.cyclo ./Core/Src/bh1750_driver.d ./Core/Src/bh1750_driver.o ./Core/Src/bh1750_driver.su ./Core/Src/commander.cyclo ./Core/Src/commander.d ./Core/Src/commander.o ./Core/Src/commander.su ./Core/Src/freertos.cyclo ./Core/Src/freertos.d ./Core/Src/freertos.o ./Core/Src/freertos.su ./Core/Src/history_buffer.cyclo ./Core/Src/history_buffer.d ./Core/Src/history_buffer.o ./Core/Src/history_buffer.su ./Core/Src/i2c_helper.cyclo ./Core/Src/i2c_helper.d ./Core/Src/i2c_helper.o ./Core/Src/i2c_helper.su ./Core/Src/main.cyclo ./Core/Src/main.d ./Core/Src/main.o ./Core/Src/main.su ./Core/Src/ntc_driver.cyclo ./Core/Src/ntc_driver.d ./Core/Src/ntc_driver.o ./Core/Src/ntc_driver.su ./Core/Src/pattern_parser.cyclo ./Core/Src/pattern_parser.d ./Core/Src/pattern_parser.o ./Core/Src/pattern_parser.su ./Core/Src/primitives.cyclo ./Core/Src/primitives.d ./Core/Src/primitives.o ./Core/Src/primitives.su ./Core/Src/reader.cyclo ./Core/Src/reader.d ./Core/Src/reader.o ./Core/Src/reader.su ./Core/Src/rules_engine.cyclo ./Core/Src/rules_engine.d ./Core/Src/rules_engine.o ./Core/Src/rules_engine.su ./Core/Src/rules_store.cyclo ./Core/Src/rules_store.d ./Core/Src/rules_store.o ./Core/Src/rules_store.su ./Core/Src/rx.cyclo ./Core/Src/rx.d ./Core/Src/rx.o ./Core/Src/rx.su ./Core/Src/sensor_dispatch.cyclo ./Core/Src/sensor_dispatch.d ./Core/Src/sensor_dispatch.o ./Core/Src/sensor_dispatch.su ./Core/Src/stm32f4xx_hal_msp.cyclo ./Core/Src/stm32f4xx_hal_msp.d ./Core/Src/stm32f4xx_hal_msp.o ./Core/Src/stm32f4xx_hal_msp.su ./Core/Src/stm32f4xx_hal_timebase_tim.cyclo ./Core/Src/stm32f4xx_hal_timebase_tim.d ./Core/Src/stm32f4xx_hal_timebase_tim.o ./Core/Src/stm32f4xx_hal_timebase_tim.su ./Core/Src/stm32f4xx_it.cyclo ./Core/Src/stm32f4xx_it.d ./Core/Src/stm32f4xx_it.o ./Core/Src/stm32f4xx_it.su ./Core/Src/syscalls.cyclo ./Core/Src/syscalls.d ./Core/Src/syscalls.o ./Core/Src/syscalls.su ./Core/Src/sysmem.cyclo ./Core/Src/sysmem.d ./Core/Src/sysmem.o ./Core/Src/sysmem.su ./Core/Src/system_stm32f4xx.cyclo ./Core/Src/system_stm32f4xx.d ./Core/Src/system_stm32f4xx.o ./Core/Src/system_stm32f4xx.su ./Core/Src/test_action_gpio.cyclo ./Core/Src/test_action_gpio.d ./Core/Src/test_action_gpio.o ./Core/Src/test_action_gpio.su ./Core/Src/test_reader_debug.cyclo ./Core/Src/test_reader_debug.d ./Core/Src/test_reader_debug.o ./Core/Src/test_reader_debug.su ./Core/Src/test_rules_debug.cyclo ./Core/Src/test_rules_debug.d ./Core/Src/test_rules_debug.o ./Core/Src/test_rules_debug.su ./Core/Src/uart_tx_queue.cyclo ./Core/Src/uart_tx_queue.d ./Core/Src/uart_tx_queue.o ./Core/Src/uart_tx_queue.su

.PHONY: clean-Core-2f-Src

