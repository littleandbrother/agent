/* STM32L031K6T6. PA0: active-low button; PB0/PB1: LEDs through individual 510 ohm.
 * Power is physically gated by BQ25570 VBAT_OK -> VOUT_EN. No GPIO is exposed
 * directly to the 4.2 V storage domain. Target build is not a hardware test.
 */
#include "stm32l0xx.h"
#include "companion_logic.h"
static volatile uint32_t ms;
static volatile uint8_t wake;
void SysTick_Handler(void){ms++;}
void EXTI0_1_IRQHandler(void){EXTI->PR=1;wake=1;}
/* No C++ or dynamic initialization in this freestanding C program. */
void __libc_init_array(void){}
int main(void){
    SystemCoreClockUpdate();
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN|RCC_IOPENR_GPIOBEN;
    RCC->APB2ENR |= RCC_APB2ENR_SYSCFGEN;
    RCC->APB1ENR |= RCC_APB1ENR_PWREN;
    GPIOA->MODER &= ~3u;
    GPIOA->PUPDR &= ~3u; /* External 1 Mohm to regulated 3 V. */
    GPIOB->MODER=(GPIOB->MODER&~15u)|5u;
    GPIOB->OTYPER &= ~3u; GPIOB->OSPEEDR &= ~15u;GPIOB->BSRR=3u<<16;
    SYSCFG->EXTICR[0]&=~15u;EXTI->RTSR|=1;EXTI->FTSR|=1;EXTI->IMR|=1;EXTI->PR=1;
    NVIC_EnableIRQ(EXTI0_1_IRQn);
    SysTick_Config(SystemCoreClock/1000u);
    companion s={READY,0,0};
    for(;;){
        int pressed=!(GPIOA->IDR&1u);
        step(&s,ms,pressed,1); /* Supply disappears below the hardware threshold. */
        GPIOB->BSRR=s.led?3u:3u<<16;
        if(s.phase==READY || (s.phase==WAIT_RELEASE&&pressed)){
            __disable_irq();
            /* Recheck pending transitions under the IRQ mask before sleeping. */
            if(!wake && pressed==(!(GPIOA->IDR&1u))){
                SysTick->CTRL&=~SysTick_CTRL_ENABLE_Msk;
                PWR->CR=(PWR->CR&~PWR_CR_PDDS)|PWR_CR_LPSDSR|PWR_CR_CWUF;
                SCB->SCR|=SCB_SCR_SLEEPDEEP_Msk;__DSB();__WFI();
                SCB->SCR&=~SCB_SCR_SLEEPDEEP_Msk;SysTick->CTRL|=SysTick_CTRL_ENABLE_Msk;
            }
            wake=0;__enable_irq();
        }
    }
}
