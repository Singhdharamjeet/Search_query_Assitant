#include <stdio.h>

int main() {
    char name[50];
    int a, b;
    printf("Enter your name: ");
    scanf("%49s", name);
    printf("First number: ");
    scanf("%d", &a);
    printf("Second number: ");
    scanf("%d", &b);
    printf("Hello, %s\n", name);
    printf("Sum = %d\n", a + b);
    return 0;
}