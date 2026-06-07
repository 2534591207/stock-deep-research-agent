# 设计文档: {变更名称}

> 版本：v1.0
> 日期：YYYY-MM-DD
> 设计者（architect role）：{填入}
> 对应 PRD：./PRD.md
> 状态：起草中 / 待验收 / 已通过 / 已实现

---

## 1. 改动范围

本次变更涉及以下层级：

- [ ] domain 层
- [ ] application 层（port / service）
- [ ] adapter/web 层
- [ ] adapter/persistence 层
- [ ] configuration / 资源文件

## 2. 领域模型变更

### 2.1 新增 / 修改的聚合根 / 实体

```
{用文字或简单 UML 描述。例如：}

Order 聚合根
├── 新增方法: cancel() -- 取消订单
│   ├── 前置条件: status == PENDING_PAYMENT
│   ├── 后置条件: status == CANCELLED, updatedAt = now()
│   └── 失败抛出: IllegalStateException("已支付的订单不能取消")
└── 修改字段: 无
```

### 2.2 新增 / 修改的 Value Object

{列出新增/修改的 VO，例如 CancellationReason。}

### 2.3 状态机（如适用）

```
PENDING_PAYMENT ──cancel()──> CANCELLED
PENDING_PAYMENT ──pay()─────> PAID
PAID            ──(cancel 拒绝)
CANCELLED       ──(终态)
```

## 3. API 设计

### 3.1 Endpoint: {METHOD PATH}

| 元素 | 内容 |
|---|---|
| **HTTP Method** | POST |
| **Path** | /api/v1/orders/{orderId}/cancel |
| **认证** | {必需 / 不必需 / 哪种 token} |
| **路径参数** | orderId: string，订单 ID |

**Request Body**:
```json
{
  "reason": "string (optional, max: 200)"
}
```

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| reason | string | 否 | maxLength=200 | 取消原因 |

**Response - Success (200 OK)**:
```json
{
  "code": 0,
  "message": "订单已取消",
  "data": {
    "orderId": "string",
    "status": "CANCELLED",
    "cancelledAt": "string (ISO 8601)"
  }
}
```

**Error Codes**:

| HTTP | code | 触发场景 | message |
|---|---|---|---|
| 400 | INVALID_PARAM | 参数校验失败（reason 超长等） | 字段级错误信息 |
| 404 | ORDER_NOT_FOUND | 订单 ID 不存在或不属于当前用户 | 订单不存在 |
| 409 | ORDER_NOT_CANCELLABLE | 订单状态不允许取消 | 当前状态不允许取消 |
| 500 | INTERNAL_ERROR | 系统异常 | 服务暂时不可用，请稍后重试 |

## 4. 应用层（Application）

### 4.1 新增 / 修改的端口（Port）

```java
// 文件路径: <SOURCE_ROOTS>/<domain-or-interface-file>
public interface CancelOrderPort {
    // 方法签名
}
```

### 4.2 新增 / 修改的应用服务（Service）

```java
// 文件路径: <SOURCE_ROOTS>/<service-or-usecase-file>
@Service
@RequiredArgsConstructor
public class CancelOrderService {
    // 依赖
    private final LoadOrderPort loadOrderPort;
    private final SaveOrderPort saveOrderPort;

    @Transactional
    public CancelOrderResult cancelOrder(CancelOrderCommand command) {
        // 编排伪代码（不写实现）：
        // 1. loadOrderPort.findById(orderId)，不存在抛 OrderNotFoundException
        // 2. 校验 order.userId == command.userId（ownership 校验）
        // 3. order.cancel()（聚合根领域方法，状态机校验）
        // 4. saveOrderPort.save(order)
        // 5. 返回 result
    }
}
```

## 5. 适配器（Adapter）

### 5.1 Web 适配器

- Controller: `CancelOrderController` at `adapter/web/order/`
- Request DTO: `CancelOrderRequest` (record)
- Response DTO: `CancelOrderResponse` (record)
- Adapter: `CancelOrderAdapter` 转换 web ↔ application

### 5.2 Persistence 适配器

{如有变化}

## 6. 状态机 / 业务规则

{如适用，绘制状态转换图 + 不变式}

## 7. 错误处理

参见 §3.x 的 error code 表格。全局异常处理由项目现有的 `@RestControllerAdvice` 类接管。

## 8. PRD 追溯表

| PRD AC ID | AC 简述 | 本文档对应章节 | 设计要点 |
|---|---|---|---|
| AC-1 | {AC 标题} | §3.1 + §4.2 | {简述} |
| AC-2 | ... | ... | ... |

## 9. 测试设计提示（给 tester）

- 单元测试：建议覆盖 {域行为 / 状态机转换}
- 集成测试：建议覆盖 {API endpoint 的 happy path 和所有 error code}
- 契约测试：{如需}

## 10. 已知问题相关性

{对照 PRD §9，本设计如何处理已知 issue}
